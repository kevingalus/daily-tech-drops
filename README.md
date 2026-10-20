# Daily Tech Drops

Automated Amazon affiliate content for Instagram [@daily_tech_drops](https://www.instagram.com/daily_tech_drops/).
Each Sunday, Claude researches the week's best-selling, well-reviewed tech products and writes every reel
and carousel into one file in `weeks/`, opened as a pull request. GitHub renders the whole week and comments
a preview. **Merging the pull request approves the week** (works from the GitHub phone app). Each product
then posts at its scheduled time, and anyone who comments **LINK** gets the affiliate link by DM.

## How a week runs

| When | Workflow | What happens |
| --- | --- | --- |
| Sunday | Claude project routine | Researches products, writes `weeks/<monday>.yaml`, opens a pull request |
| On that pull request | `Render week` | Renders every reel and carousel, stores them on the `media` branch, comments a preview |
| You merge | | The week is approved |
| Every 30 min | `Post and reply` | Posts the next product whose time has come; DMs the link to keyword comments |
| Sunday late morning | `Weekly report` | Measures the last 7 days per post and lane, saves `reports/latest.md` for the Sunday research, opens an issue with the report |
| 1st of the month | `Refresh Instagram token` | Renews the 60-day Instagram token |

**Sunday research, read this:** if `reports/latest.md` exists, it is last week's performance report. Weight the new
week toward the lanes, product types and hooks that earned the most link DMs, saves and shares, and away from the
weakest, while still rotating lanes. Open the week's pull request body with two or three lines on what the report
showed and how it shaped the picks.

A post more than 6 hours late (for example, a week merged on Tuesday) is skipped rather than posted late.
To pull one product, delete it from the week file before its time.

## One-time setup

### 1. Repository secrets and variables
Settings > Secrets and variables > Actions.

| Secret | Where to get it | Required |
| --- | --- | --- |
| `AMAZON_TAG` | Amazon Associates > tracking ID, e.g. `dailytechdrops-20` | Yes |
| `IG_USER_ID` | From the Meta app setup below | Yes |
| `IG_ACCESS_TOKEN` | From the Meta app setup below (long-lived token) | Yes |
| `PIXABAY_API_KEY` | pixabay.com/api/docs (free account; the key is shown on that page once logged in) | Recommended (plain branded backgrounds without a footage key) |
| `PEXELS_API_KEY` | pexels.com/api (free, but new keys were paused when we tried in Oct 2026) | Optional alternative to Pixabay |
| `ANTHROPIC_API_KEY` | console.anthropic.com (paid) | No. Only for products without pre-written content |
| `ELEVENLABS_API_KEY` | elevenlabs.io (paid for commercial use) | No. Only if `voice.provider` is `elevenlabs` |
| `GH_PAT` | GitHub fine-grained token, this repo only, "Secrets: read and write" | For the monthly token refresh |

| Variable | Value |
| --- | --- |
| `MEDIA_BASE_URL` | Only if the carousel images are hosted somewhere other than this repo's `media` branch |
| `KEYWORD_DMS` | `off` if you use Instagram's built-in keyword auto-reply instead |

### 2. Meta app (lets the code post and DM)
1. Instagram account must be **Professional** (Creator or Business).
2. developers.facebook.com > My Apps > Create app > use case **Manage messaging and content on Instagram**.
3. Under *API setup with Instagram login*, add the Instagram account and generate a token with:
   `instagram_business_basic`, `instagram_business_content_publish`,
   `instagram_business_manage_comments`, `instagram_business_manage_messages`,
   `instagram_business_manage_insights` (for the weekly report).
4. Copy the Instagram user ID and the token into the secrets above.
5. While the app is in Development mode it works for your own account, which is all this needs.

### 3. Carousel images must be public
Instagram downloads carousel images from a URL. Reels upload directly and do not need this.
The default URL is this repo's `media` branch, which only works if the **repository is public**.
Nothing secret lives in the code; keys stay in GitHub secrets. Public repos also get unlimited Actions minutes.
If the repo stays private, set `MEDIA_BASE_URL` to another public host, or the carousel step fails while the reel still posts.

### 4. Music (optional)
Drop royalty-free `.mp3` files in `assets/music/`. One is picked at random per reel and mixed under the voice.
Use tracks you have the rights to (for example YouTube Audio Library or a Pixabay music download).

## Cost

Everything in the default setup is free: GitHub Actions (unlimited on a public repo), the Instagram API,
Pixabay or Pexels footage, and the Piper voice, which runs on GitHub's machines. Scripts are pre-written in
the week files from the Claude project, so no paid AI API is needed. ElevenLabs voices and the Claude API
are optional upgrades.

## Week files
Each entry in `weeks/<monday>.yaml` has a `slot` ("YYYY-MM-DD HH:MM", Eastern), the ASIN (from
`amazon.com/dp/<ASIN>`), name, lane, angle, verified facts, stock footage ideas, and a `content` block with
the beats, slides, caption, hashtags and DM text. See `weeks/2026-10-26.yaml` for the shape.
Posts never state prices because prices change daily.

## Running locally
```bash
pip install -r requirements.txt   # plus ffmpeg on your PATH
python -m dtd render --week weeks/2026-10-26.yaml   # writes output/<id>/ per product
```
With no API keys set it still renders a full draft using the template, which is a free way to test changes.

## Rules this follows
- Every caption starts with `#ad As an Amazon Associate I earn from qualifying purchases.` (FTC and Amazon).
- No Amazon product photos: the Associates agreement limits reuse of Amazon images. Visuals are stock footage and branded text.
- Posting and DMs go through Instagram's official API only.
