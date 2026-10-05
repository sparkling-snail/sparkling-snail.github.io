# sparkling-snail.github.io

Personal site, built with Hugo and deployed to GitHub Pages on every push to `main`.
Live at https://sparkling-snail.github.io/teoweetin/ (the bare domain redirects there).

## Local preview

    brew install hugo
    hugo server -D        # -D also shows drafts; open http://localhost:1313

## New content

    hugo new posts/my-post.md          # blog post (starts as a draft)
    hugo new projects/my-project.md    # project case study

Set `draft: false` in a post's front matter to publish it, then `git push`.

Images go in `static/images/` and are referenced as `/images/name.png`.

## Customise

- `hugo.toml`: name, tagline, LinkedIn/email, résumé link, avatar, and the highlights row on the homepage.
- `static/resume.pdf` + `resume = "resume.pdf"` in `hugo.toml` adds a Résumé button.
- Covers: set `image:` in a page's front matter, or `glyph:` to change the text on the generated cover.
- Diagrams: use a ```` ```mermaid ```` code block in any page.
- Colours and animation: `static/css/style.css` (theme tokens at the top).
