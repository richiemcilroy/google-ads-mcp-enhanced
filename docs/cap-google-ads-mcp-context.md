# Cap Google Ads MCP Context

This document records the local Codex setup for Cap's Google Ads MCP integration. It intentionally excludes developer tokens, OAuth secrets, refresh tokens, and credential contents.

## Repository and MCP Setup

- Fork: `https://github.com/richiemcilroy/google-ads-mcp-enhanced`
- Local repo: `/Users/richie/Documents/github/google-ads-mcp-enhanced`
- Default branch for Cap changes: `main`
- Upstream source repo: `https://github.com/googleads/google-ads-mcp.git`
- Codex MCP server name: `google-ads-mcp-enhanced`
- Local launcher: `/Users/richie/.codex/google-ads-mcp-enhanced`
- Login helper: `/Users/richie/.codex/google-ads-mcp-enhanced-login`
- Env file: `/Users/richie/.codex/google-ads-mcp-enhanced.env`
- Tools config: `/Users/richie/.codex/google-ads-mcp-enhanced-tools-config.yaml`
- OAuth client JSON path: `/Users/richie/.codex/google-ads-oauth-client.json`

## Cap Google Ads Account

- Customer ID: `3769134291`
- Display name verified on 2026-06-09: `Cap`
- Currency verified on 2026-06-09: `USD`
- Time zone verified on 2026-06-09: `America/Los_Angeles`

## Verified Access on 2026-06-09

The following API paths were verified through the MCP against customer `3769134291`:

- Accessible customer discovery returned `3769134291`.
- Read-only `customer` query returned the Cap account metadata.
- Read-only `campaign` query succeeded and returned no campaign rows.
- Keyword historical metrics worked for `screen recorder` and `loom alternative`.
- A `validate_only=true` campaign budget mutation succeeded and created no resources.

If a future session sees `Reauthentication is needed`, run:

```shell
/Users/richie/.codex/google-ads-mcp-enhanced-login
```

Then rerun accessible-customer discovery and a small `customer` query.

## Tool Namespaces

The local tools config enables all namespaces:

- `customers`
- `search`
- `metadata`
- `planning`
- `reports`
- `recommendations`
- `conversions`
- `mutations`

Mutation tools are visible so they can be dry-run through Google Ads validation. Real writes remain blocked unless the MCP environment enables them.

## Write Guardrails

Default to read-only actions unless the operator explicitly asks for changes.

For any write-capable tool:

- Use `validate_only=true` first.
- Do not use `validate_only=false` without explicit approval for the exact change.
- Real writes require `GOOGLE_ADS_MCP_ENABLE_MUTATIONS=true`.
- Real `ENABLED` status changes require `GOOGLE_ADS_MCP_ALLOW_ENABLE=true`.
- Respect `GOOGLE_ADS_MCP_MAX_DAILY_BUDGET_MICROS` and `GOOGLE_ADS_MCP_MAX_CPC_BID_MICROS` if set.

Do not print, commit, or summarize the developer token, OAuth secret, refresh token, ADC file contents, or env file values.

## Operating Workflow

For campaign work:

1. Use read-only reporting and planning tools to gather facts.
2. Draft the campaign structure, budgets, keywords, negatives, and ad copy.
3. Run mutation tools with `validate_only=true`.
4. Report the exact validation result and planned operations.
5. Apply only after explicit approval and only if environment guardrails allow real writes.

For analysis work:

1. Start with Google Ads data from MCP.
2. Combine with product analytics, Stripe, and Cap repo context only when needed.
3. Separate verified facts from recommendations.
4. Keep spend recommendations tied to CAC, conversion tracking quality, and campaign intent.

## Cap Acquisition Context

At the start of paid acquisition planning, Cap revenue was about `$18k/mo`, all organic. The initial recommendation was to start with Google Search rather than cold Meta. Meta may still be useful for retargeting and creative validation.

Useful initial Search themes:

- `loom alternative`
- `open source loom`
- `screen recorder`
- `screen recorder no watermark`
- privacy-focused screen recording
- developer/team screen recording
- self-hosted or compliance-oriented screen recording

Previous rough CAC guardrails:

- Monthly Pro: under roughly `$40-$60`
- Annual Pro: under roughly `$80-$120`

Before scaling spend, confirm attribution captures Google click IDs and server-side purchases correctly.
