"""SEO module (ARCHITECTURE §4, §16): redirects, the `seo` JSON checks and warnings shared by
projects, pages and posts, and the public paths of content (for redirects on slug changes).

TODO(phase-5): `/api/v1/public/redirects` (read by the web app's middleware, which also counts
`hits` and `last_hit_at`) and `/api/v1/public/sitemap`.
"""
