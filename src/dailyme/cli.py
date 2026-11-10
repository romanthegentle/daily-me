"""The `dailyme` command."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from importlib.resources import files
from pathlib import Path

import anthropic

from . import __version__
from .history import History
from .models import Edition
from .profile import Delivery, example_profile_text, load_profile

log = logging.getLogger("dailyme")


def publish(
    edition: Edition, delivery: Delivery, *, out: str, send: bool, pdf: bool
) -> dict[str, Path]:
    """Write the edition's files, print a PDF if asked, and email it if asked."""
    from .render import print_pdf, render_email, render_markdown, write_edition

    paths = write_edition(edition, out)
    pdf_path: Path | None = None
    if pdf or delivery.pdf or delivery.attach_pdf:
        candidate = paths["html"].with_suffix(".pdf")
        if print_pdf(paths["html"], candidate):
            pdf_path = paths["pdf"] = candidate
        else:
            log.warning("No PDF: install Chrome or Edge, or point DAILYME_BROWSER at one.")
    for kind, path in paths.items():
        print(f"  {kind:<8} {path}")

    if send:
        from .deliver import EmailSettings, build_message, send_message, subject_for

        try:
            settings = EmailSettings.from_env()
        except ValueError as error:
            log.warning("Not sent: %s.", error)
            return paths
        message = build_message(
            edition,
            settings,
            subject=subject_for(edition, delivery.subject),
            html=render_email(edition),
            text=render_markdown(edition),
            attachment=pdf_path if delivery.attach_pdf else None,
        )
        send_message(message, settings)
        count = len(settings.recipients)
        print(f"Sent to {count} recipient{'s' if count != 1 else ''}.")
    return paths


def cmd_run(args: argparse.Namespace) -> int:
    from .llm import Claude
    from .pipeline import build_edition

    profile = load_profile(args.profile)
    claude = Claude(
        profile.settings.model, profile.settings.effort, fallbacks=profile.settings.fallbacks
    )
    history = History.load(args.state)
    edition = build_edition(profile, claude, history)
    print(f"{edition.paper_name} No. {edition.number}: {len(edition.articles())} stories.")
    publish(edition, profile.delivery, out=args.out, send=args.send, pdf=args.pdf)
    history.record(edition)
    history.save()
    print(f"Cost: {claude.usage.summary(claude.model)}.")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    edition = Edition.model_validate_json(Path(args.edition).read_text(encoding="utf-8"))
    delivery = Delivery()
    if args.profile:
        profile = load_profile(args.profile)
        delivery = profile.delivery
        if edition.weather is None:
            from .weather import forecast

            edition.weather = forecast(profile.reader.location)
    history = History.load(args.state) if args.state else None
    if history is not None:
        edition.number = history.number_for(date.fromisoformat(edition.date))
    publish(edition, delivery, out=args.out, send=args.send, pdf=args.pdf)
    if history is not None:
        history.record(edition)
        history.save()
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .render import write_edition

    sample = files("dailyme").joinpath("sample/sample-edition.json").read_text(encoding="utf-8")
    paths = write_edition(Edition.model_validate_json(sample), args.out)
    print(f"Sample edition written to {paths['html']}. Open it in your browser.")
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    target = Path(args.path)
    if target.exists() and not args.force:
        print(f"{target} already exists. Use --force to replace it.", file=sys.stderr)
        return 1
    if args.from_text:
        from .llm import Claude
        from .onboarding import draft_profile, profile_yaml

        text = Path(args.from_text).read_text(encoding="utf-8")
        target.write_text(profile_yaml(draft_profile(text, Claude(args.model))), encoding="utf-8")
    else:
        target.write_text(example_profile_text(), encoding="utf-8")
    print(f"Wrote {target}. Make it yours, then run `dailyme run`.")
    return 0


def cmd_schema(args: argparse.Namespace) -> int:
    print(json.dumps(Edition.model_json_schema(), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dailyme", description="Your own AI-written newspaper, every morning."
    )
    parser.add_argument("--version", action="version", version=f"dailyme {__version__}")
    parser.add_argument("-q", "--quiet", action="store_true", help="only print warnings")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser("run", help="research, write and lay out today's edition")
    run.add_argument("--profile", help="profile file (default: profile.yaml or $DAILYME_PROFILE)")
    run.add_argument("--out", default="editions", help="where to save editions (default: editions)")
    run.add_argument(
        "--state", default="state", help="where to keep story history (default: state)"
    )
    run.add_argument(
        "--send", action="store_true", help="email it (needs the DAILYME_SMTP_* settings)"
    )
    run.add_argument("--pdf", action="store_true", help="also print a PDF (needs Chrome or Edge)")
    run.set_defaults(handler=cmd_run)

    render = commands.add_parser(
        "render", help="lay out an edition JSON, such as one from Claude Code"
    )
    render.add_argument("edition", help="path to the edition JSON")
    render.add_argument("--profile", help="profile file, for the email subject and PDF settings")
    render.add_argument("--out", default="editions", help="where to save it (default: editions)")
    render.add_argument("--state", help="record its stories in this history folder")
    render.add_argument("--send", action="store_true", help="email it")
    render.add_argument("--pdf", action="store_true", help="also print a PDF")
    render.set_defaults(handler=cmd_render)

    demo = commands.add_parser("demo", help="lay out the bundled sample edition; no API key needed")
    demo.add_argument("--out", default="editions", help="where to save it (default: editions)")
    demo.set_defaults(handler=cmd_demo)

    init = commands.add_parser("init", help="create profile.yaml")
    init.add_argument("--path", default="profile.yaml", help="where to write it")
    init.add_argument(
        "--from-text", help="draft the profile from a description of you, such as your AI's memory"
    )
    init.add_argument("--model", default="claude-opus-5-5", help="model for --from-text")
    init.add_argument("--force", action="store_true", help="replace an existing profile")
    init.set_defaults(handler=cmd_init)

    schema = commands.add_parser("schema", help="print the edition JSON schema")
    schema.set_defaults(handler=cmd_schema)
    return parser


def _utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING if args.quiet else logging.INFO, format="%(message)s")
    try:
        return args.handler(args)
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
    except anthropic.AuthenticationError:
        print(
            "error: the Claude API rejected the credentials. Set ANTHROPIC_API_KEY "
            "(https://console.anthropic.com) and try again.",
            file=sys.stderr,
        )
    except anthropic.AnthropicError as error:
        print(f"error: {error}", file=sys.stderr)
    except ValueError as error:  # includes invalid profiles and editions
        print(f"error: {error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
