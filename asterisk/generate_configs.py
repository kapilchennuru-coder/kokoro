# =============================================================
# Regenerates config/pjsip.conf and config/manager.conf from their
# .template files, substituting in the real credentials from .env.
#
# Asterisk's own config files can't read environment variables
# directly, so THIS script is the actual bridge: .env is the source
# of truth for credentials, the .template files are the source of
# truth for structure, and config/*.conf (what Asterisk actually
# reads) is generated output - never hand-edit those two files
# directly, edit the .env or .template instead and re-run this.
#
# Run this any time .env or a .template file changes, then restart
# the Asterisk container to pick up the regenerated config.
# =============================================================

import os

from dotenv import dotenv_values

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
ENV_PATH = os.path.join(BASE_DIR, ".env")

TEMPLATES = ["pjsip.conf", "manager.conf"]


def render_template(template_text: str, values: dict) -> str:
    rendered = template_text
    for key, value in values.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value or "")
    return rendered


def main():
    values = dict(dotenv_values(ENV_PATH))

    # CONFIRMED REAL BUG (2026-08-05, re-confirmed 2026-08-06): if the
    # SIP username is an email address, it already contains its own
    # '@' - the templates below insert it directly into SIP URIs
    # (sips:USERNAME@SERVER), which becomes an invalid double-'@' URI
    # if not escaped. Percent-encoding ('%40') the '@' ONLY for the
    # URI-embedded placeholder fixes this regardless of what username
    # format ends up in .env - the auth username= field (which isn't
    # a URI, just a plain credential string) keeps the raw value.
    username = values.get("VOIP_OFFICE_USERNAME") or ""
    values["VOIP_OFFICE_USERNAME_URI"] = username.replace("@", "%40")

    for name in TEMPLATES:
        template_path = os.path.join(CONFIG_DIR, f"{name}.template")
        output_path = os.path.join(CONFIG_DIR, name)

        with open(template_path, "r", encoding="utf-8") as f:
            template_text = f.read()

        rendered = render_template(template_text, values)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(rendered)

        print(f"Generated {output_path} from {template_path}")


if __name__ == "__main__":
    main()
