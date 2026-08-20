# Public reviewer fixture specification

The reviewer fixture must be hosted at a stable HTTPS URL owned/controlled by the project and contain only artwork/text that the project is allowed to distribute for review.

Minimum cases on one deterministic page:

- normal `<img>` comic panel;
- `picture/srcset` or lazy image;
- visible dialogue and narration in English;
- at least one annotated SFX region that must remain pixel-identical;
- a second image loaded near the viewport;
- a small cross-origin CDN case only if the release reviewer path needs to demonstrate exact-origin permission;
- no login, paywall, anti-bot challenge, or third-party copyright dependency.

The fixture should publish its expected source SHA-256 values and expected translated-result validation metadata so reviewer smoke results can be recorded without exposing private user content.
