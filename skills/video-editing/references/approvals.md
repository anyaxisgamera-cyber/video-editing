# Approvals, website access, and consequential actions

Autonomous production does not mean acting on the user's behalf in ways they have not agreed to. Proceed without asking for read-only work; ask explicitly before anything that costs money, creates obligations, shares data, or publishes.

## No approval needed

- Reading public web pages, search results, documentation, and public APIs that need no key.
- Downloading assets whose item-level licence permits the intended use, without login or payment, where the site's terms allow downloading.
- Local work: analysis, editing, rendering, validation, and drafting reports.

## Explicit approval required

Ask before:

- purchases, paid downloads, subscriptions, trials that convert to paid, or paid API usage;
- creating an account, signing in with new credentials, or connecting an OAuth app;
- accepting terms on the user's behalf (gated models, licence agreements, marketplace terms);
- uploading anything to an external service (files, scripts, voice samples, footage);
- publishing, posting, scheduling, or sharing outside the private workspace;
- using an asset whose licence carries a restriction the user may not accept (non-commercial, share-alike, editorial-only, attribution on screen);
- voice cloning or using a real person's likeness or voice;
- any other action that is hard to reverse.

Never ask the user to paste passwords or API keys into chat. Use the environment's secure credential mechanism when one exists; otherwise ask the user to set an environment variable themselves.

## Approval request format

Present each request on its own, with everything needed to decide:

| Field | Content |
|---|---|
| Website / service | name and exact URL |
| Purpose | what it unlocks for this production and which scenes or deliverables depend on it |
| Cost | price, billing period, free-tier limits, cancellation terms — checked on the official pricing page, with the date |
| Permissions and data | account creation, OAuth scopes, what is uploaded or shared, where it is stored |
| Restrictions | licence and terms that matter: commercial use, attribution, territory, redistribution, AI-training clauses |
| Alternatives | what happens if declined, including free alternatives and their trade-offs |

Record every request and the user's answer in `research/approvals.json`:

```json
{"id": "ap03", "requested_at": "…", "service": "…", "url": "…", "purpose": "…",
 "cost": "…", "permissions": "…", "restrictions": "…", "decision": "approved",
 "decided_at": "…", "user_words": "…"}
```

An approval covers only what it states. A later, different action needs a new request. If the user declines, use the alternative and note the impact in the production report.

## Respect access controls

Follow each site's terms and robots rules. Do not scrape where an API is required, bypass bot challenges, paywalls, or rate limits, or download streams that the site does not offer for download. When the environment's own network policy blocks a host, request access through the environment's mechanism rather than working around it.
