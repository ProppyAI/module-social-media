# module-social-media

HARNESS module: social media post creation and scheduling.

## Entity Contract

- **Produces:** social-post
- **Consumes:** content-asset, job

## Tools

| Tool | Description |
|------|-------------|
| create-post | Create a social media post from a content asset |
| schedule-post | Schedule a post for future publishing |
| publish-post | Publish a post to the platform |

## Hooks

- `ContentAssetCreated` -> `auto-create-draft-post`: Auto-creates a draft post when a content asset is generated.

## Cron

- `weekly-content-calendar` (Mondays 9am): Plan next week's social media content calendar.

## Platforms

Supported: Instagram, Facebook, Google Business, TikTok.

## Setup

Bootstrap with HARNESS:

```bash
HARNESS_LOCAL=/path/to/HARNESS bash /path/to/HARNESS/bin/harness-init
```
