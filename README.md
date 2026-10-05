# sparkling-snail.github.io

Personal site, built with Hugo and deployed to GitHub Pages on every push to `main`.

## Local preview

    brew install hugo
    hugo server -D        # -D also shows drafts; open http://localhost:1313

## New content

    hugo new posts/my-post.md          # blog post (starts as a draft)
    hugo new projects/my-project.md    # project case study

Set `draft: false` in a post's front matter to publish it, then `git push`.

Images go in `static/images/` and are referenced as `/images/name.png`.
