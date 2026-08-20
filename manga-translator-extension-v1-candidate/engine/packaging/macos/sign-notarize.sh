#!/usr/bin/env bash
set -euo pipefail
: "${MTE_DEVELOPER_ID_APPLICATION:?Set MTE_DEVELOPER_ID_APPLICATION}"
: "${MTE_DEVELOPER_ID_INSTALLER:?Set MTE_DEVELOPER_ID_INSTALLER}"
ROOT_PATH="${1:?usage: sign-notarize.sh <onedir> <output.pkg>}"
OUTPUT_PKG="${2:?usage: sign-notarize.sh <onedir> <output.pkg>}"

NOTARY_ARGS=()
if [[ -n "${MTE_NOTARY_KEY_PATH:-}" || -n "${MTE_NOTARY_KEY_ID:-}" || -n "${MTE_NOTARY_ISSUER_ID:-}" ]]; then
  : "${MTE_NOTARY_KEY_PATH:?Set MTE_NOTARY_KEY_PATH for API-key notarization}"
  : "${MTE_NOTARY_KEY_ID:?Set MTE_NOTARY_KEY_ID for API-key notarization}"
  : "${MTE_NOTARY_ISSUER_ID:?Set MTE_NOTARY_ISSUER_ID for API-key notarization}"
  test -s "$MTE_NOTARY_KEY_PATH"
  NOTARY_ARGS=(--key "$MTE_NOTARY_KEY_PATH" --key-id "$MTE_NOTARY_KEY_ID" --issuer "$MTE_NOTARY_ISSUER_ID")
elif [[ -n "${MTE_NOTARY_PROFILE:-}" ]]; then
  NOTARY_ARGS=(--keychain-profile "$MTE_NOTARY_PROFILE")
else
  echo 'Configure API-key notarization (MTE_NOTARY_KEY_PATH/KEY_ID/ISSUER_ID) or MTE_NOTARY_PROFILE.' >&2
  exit 2
fi

STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT
cp -R "$ROOT_PATH" "$STAGE/mte-engine"
while IFS= read -r -d '' file_path; do
  if file "$file_path" | grep -q 'Mach-O'; then
    codesign --force --options runtime --timestamp --sign "$MTE_DEVELOPER_ID_APPLICATION" "$file_path"
    codesign --verify --strict --verbose=2 "$file_path"
  fi
done < <(find "$STAGE/mte-engine" -type f -print0)
pkgbuild --root "$STAGE/mte-engine" --install-location '/Applications/Manga Translator Engine' --identifier 'org.mte.local-engine' --version '0.5.0' "$STAGE/unsigned.pkg"
productsign --sign "$MTE_DEVELOPER_ID_INSTALLER" "$STAGE/unsigned.pkg" "$OUTPUT_PKG"
pkgutil --check-signature "$OUTPUT_PKG"
xcrun notarytool submit "$OUTPUT_PKG" "${NOTARY_ARGS[@]}" --wait
xcrun stapler staple "$OUTPUT_PKG"
xcrun stapler validate "$OUTPUT_PKG"
echo "$OUTPUT_PKG"
