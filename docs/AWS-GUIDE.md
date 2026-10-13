# WebScout-RAG on AWS — beginner guide (GitHub + Docker + CloudFormation)

Read **Part A** once (the ideas). Then follow **Part B** step by step (the doing).

---

## PART A — The ideas, in plain words

### A1. The big picture

```
You push code to GitHub
        │
        ▼
GitHub Actions (a free robot computer)
   1. runs tests
   2. builds Docker IMAGES from your Dockerfiles
   3. uploads images to AWS ECR (a storage shelf for images)
   4. tells your server: "pull the new images and restart"
        │
        ▼
AWS EC2 server (one small computer in AWS, created by CloudFormation)
   Docker Compose runs 3–4 CONTAINERS:
     frontend (nginx)  ← the website + forwards /api to backend
     backend  (FastAPI) ← scraping, AI search, answers
     redis             ← fast memory: cache, queue, rate limit
     caddy             ← free HTTPS (optional)
```

### A2. Containerization (Docker)

Problem: "it works on my laptop" but not on the server (different Python version, missing Chromium…).
Solution: package the app **plus everything it needs** into one sealed box.

| Word | Meaning | In your project |
|---|---|---|
| **Dockerfile** | The recipe: "start from Python 3.11, install these libraries, copy my code, run this command" | `backend/Dockerfile`, `frontend/Dockerfile` |
| **Image** | The finished, frozen box made from the recipe | `webscout-backend`, `webscout-frontend` |
| **Container** | A running copy of an image | what runs on the server |
| **Registry (ECR)** | A shelf where images are stored so the server can download them | 2 ECR repositories |
| **docker-compose.yml** | A file that starts several containers together and connects them | `docker-compose.yml` |

Your `frontend/Dockerfile` is a nice example of a **multi-stage build**: stage 1 uses Node to build the React site, stage 2 copies only the finished files into a tiny nginx image. The final image doesn't contain Node at all.

### A3. CloudFormation ("Infrastructure as Code")

Without it: you click ~40 things in the AWS console and can't remember what you did.
With it: one text file (`deploy/cloudformation.yml`) says "I want a server, a firewall, two image repos, these permissions". You upload it and AWS builds it all. Delete the **stack** and AWS removes everything it built → no forgotten, billable leftovers. That is why it's perfect for a free-tier learner.

Words: **Template** = the file · **Stack** = the group of things created from it · **Parameters** = blanks you fill (your repo name, Groq key) · **Outputs** = answers it gives back (server IP, role ARN).

### A4. What does "group" mean? (you'll meet three)

| Group | What it is | Needed here? |
|---|---|---|
| **Security group** | The server's **firewall**: which ports the internet may knock on (80 = web, 443 = secure web). | **Yes** — created by the template |
| **Auto Scaling group** | "Keep N servers alive; add more when busy, replace dead ones." | No (see A6) |
| **Target group** | The list of servers a load balancer sends visitors to. | No (see A6) |

If you meant something else by "group", tell me and I'll cover it.

### A5. Redis, caching, and "the query" — what happens in *your* app

**Redis** = a database that lives in RAM. Extremely fast (microseconds), but small and for temporary data. Your app uses it for four jobs (all in `backend/app/main.py`):

| Job | How | Why it matters |
|---|---|---|
| **Cache** | After scraping a URL, it saves `page:<id>` with a 6-hour timer (`CACHE_TTL`). Next time someone pastes the same URL → answer is instant, no scraping. | Scraping + AI embedding takes 20–40 s. Cache = 0 s. |
| **Job queue** | `/api/ingest` pushes a job id onto a list (`rpush`); a worker pops it (`blpop`), one at a time. | A 1 GB server can't scrape 5 sites at once. A queue makes people wait in line instead of crashing the server. |
| **Rate limiter** | Counts requests per IP per minute (`incr` + `expire`). Over 30 → "slow down". | Protects your free Groq quota from abuse. |
| **Job status** | Stores `queued → running → ready` so the website can show progress. | Browser polls `/api/jobs/<id>`. |

**Caching in general** = "remember the answer to expensive work so you don't redo it." Your app has *two* caches: Redis (which pages were already processed) and an in-memory cache of the last 3 vector files (`vectorstore.py`).

**The query** (what happens when you ask a question) — this is **RAG**, "Retrieval-Augmented Generation":

1. At ingest time the page is cut into ~1000-character **chunks**; each chunk is turned into a list of numbers (an **embedding**) that represents its *meaning*.
2. Your question is turned into numbers the same way.
3. **Vector search**: find the 20 chunks whose numbers are closest to the question's.
4. **Re-ranker**: a smarter (slower) model reads question + each chunk together and keeps the best 5.
5. Those 5 chunks + your question go to the LLM (Groq) with the rule "answer only from these, cite [1][2]".
6. If no chunk is relevant, the LLM is not called at all → no made-up answer.

### A6. Load balancing — why, and do *you* need it?

**What:** a **load balancer (LB)** is a receptionist standing in front of several identical servers. Visitors talk to the receptionist, who hands each one to a free server.

**Why companies use it**
1. **Capacity** — one server handles ~N users; ten servers handle ~10N.
2. **No downtime** — if a server dies, the LB stops sending people to it (it keeps checking "are you healthy?").
3. **Safe updates** — update servers one by one while the others keep serving.
4. **One front door** — HTTPS certificates and the public address live on the LB.

On AWS this is an **ALB** (Application Load Balancer) + a **target group** (its list of servers) + usually an **Auto Scaling group** (which creates/removes the servers).

**Do you need it? Not yet — honestly, no.**
- An ALB costs about **$16+/month** and is *not* covered by always-free limits (new accounts burn their credits on it).
- **Your app is not ready to be copied.** Vectors are files on one server's disk (`/data`), jobs are scraped by one Chromium, sign-in sessions are stored on that disk. If a 2nd server existed, user A could scrape on server 1 and then be sent to server 2, which has never heard of that page.
- Your real bottleneck is the **1 GB RAM**, and the app already handles it with a queue + cache.

**What you'd change to make it scale later:** move vectors to shared storage (S3, or a database with pgvector), move Redis to a shared one (ElastiCache), then add ALB + target group + Auto Scaling group. Nginx in your `frontend` container is already a tiny *reverse proxy* — the same idea of "one front door that forwards to something behind it", just with one server behind it.

### A7. Free tier — the honest version

- New AWS accounts now typically get a **free plan with credits (~6 months)** rather than "12 months free". Check **Billing → Free tier** in your console for your exact numbers. (Details change; I couldn't confirm current exact amounts, so trust the console.)
- This setup uses: 1 small EC2 (free-tier eligible type), 20 GB disk, 1 Elastic IP (free while attached to a running server), ECR storage (a few cents — images are ~2 GB).
- **Not free / avoid:** load balancers, NAT gateways, bigger instances, forgetting to delete the stack.
- You mentioned the "free root" method: that's fine for a free account, but **sign in as root only to set things up.** Turn on **MFA** for root (Account menu → Security credentials → Assign MFA) and create a **budget alert** (Billing → Budgets → "Zero spend budget") so you get an email if anything costs money.

---

## PART B — Do it, step by step

### Step 0 — Accounts and tools (10 min)
1. **AWS account** — https://aws.amazon.com (free plan). Pick one region (e.g. **us-east-1**) in the top-right of the console and **use it for everything**.
2. **GitHub account** — https://github.com
3. **Groq API key** — https://console.groq.com/keys → Create API Key (starts `gsk_`).
4. **Git** (https://git-scm.com) and **Docker Desktop** (https://www.docker.com/products/docker-desktop) on your computer.

### Step 1 — Run it locally with Docker first (15–20 min)
This proves your containers work *before* touching AWS.
```bash
cd webscout-rag
cp .env.example .env        # Windows PowerShell: copy .env.example .env
# open .env, put your real GROQ_API_KEY=gsk_...
docker compose up --build
```
Wait for `models loaded`, open **http://localhost**, paste a Wikipedia URL, ask a question. `Ctrl+C` to stop.
*If this fails, fix it here — it's far easier than debugging on a server.*

### Step 2 — Put the code on GitHub (5 min)
1. github.com → **New repository** → name `webscout-rag` → **Public** (the server downloads the code with a plain `git clone`; your keys are safe because `.env` is git-ignored).
2. In the project folder:
```bash
git init
git add .
git commit -m "first commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/webscout-rag.git
git push -u origin main
```
3. On github.com confirm **`.env` is not listed** (only `.env.example`).

> The first push will make GitHub Actions run and **fail at the AWS steps** — expected, AWS isn't set up yet. The test job should be green.

### Step 3 — Create everything on AWS with CloudFormation (10 min)
1. AWS Console → search **CloudFormation** → **Create stack → With new resources**.
2. **Upload a template file** → choose `deploy/cloudformation.yml` → Next.
3. Stack name: `webscout`. Fill the parameters:
   - **GitHubRepo** → `YOUR_USERNAME/webscout-rag`
   - **GroqApiKey** → your `gsk_...`
   - **InstanceType** → `t3.micro` (or `t2.micro` if that's what EC2 labels "Free tier eligible" for you)
   - **EnableHttps** → `true`
   - **CreateGitHubOidcProvider** → `true` (use `false` only if the stack later fails with *"already exists"*)
4. Next → Next → tick **"I acknowledge that AWS CloudFormation might create IAM resources with custom names"** (it creates roles) → **Submit**.
5. Watch the **Events** tab until the status is **CREATE_COMPLETE** (~3–5 min). If it says ROLLBACK, open Events, find the red line — that is the reason (see Troubleshooting).
6. Open the **Outputs** tab. Keep it open: you need **InstanceId**, **GitHubRoleArn**, **Region**, **AppUrl**.

> CloudFormation finishes when the server *exists*, not when the software is installed. The server keeps installing Docker, swap, and your code for **another ~5 minutes**. Wait before Step 5.

### Step 4 — Tell GitHub how to reach AWS (3 min)
GitHub repo → **Settings → Secrets and variables → Actions → Variables tab → New repository variable**. Add three (copy from the stack Outputs):

| Name | Value |
|---|---|
| `AWS_ROLE_ARN` | Outputs → GitHubRoleArn |
| `AWS_REGION` | Outputs → Region (e.g. `us-east-1`) |
| `AWS_INSTANCE_ID` | Outputs → InstanceId (`i-0abc…`) |

No passwords or access keys are stored in GitHub. GitHub proves who it is to AWS using a short-lived token (OIDC), and the role only works for **your repo's main branch**.

### Step 5 — Deploy (15 min the first time)
Check the server is ready: AWS Console → **Systems Manager → Fleet Manager** → your instance should say **Online**. (Not there yet? wait 2–3 min.)

Then in your project folder:
```bash
git commit --allow-empty -m "deploy"
git push
```
GitHub repo → **Actions** tab → watch **test → build-and-push → deploy**. First run ≈ 10–15 min (Chromium + AI models are baked into the backend image). Later runs are faster thanks to layer reuse on the server (and the same on your side).

Or re-run the failed run from Step 2: Actions → the run → **Re-run all jobs**.

### Step 6 — Open the app
Stack Outputs → **AppUrl** (looks like `https://3-90-12-45.sslip.io`). The first HTTPS load can take ~30 s while Caddy gets a free Let's Encrypt certificate. With `EnableHttps=true`, plain `http://` addresses are automatically redirected to HTTPS. (With `false`, use **AppUrlPlainHttp**.)

From now on, **every push to `main` redeploys automatically.**

### Step 7 — Look inside the server (when something is wrong)
No SSH key needed: Stack Outputs → **OpenServerShell** (or EC2 → select instance → Connect → **Session Manager**). Then:
```bash
sudo -i
cd /opt/webscout
docker compose ps                 # which containers are running
docker compose logs -f backend    # live backend log (Ctrl+C to exit)
docker compose logs caddy         # HTTPS certificate problems show here
free -h                           # RAM + swap (swap should show 3 GB)
cat /var/log/webscout-bootstrap.log   # the first-boot install log
```

### Step 8 — Cleanup (so nothing keeps billing)
CloudFormation → select `webscout` → **Delete**. It removes the server, IP, firewall, roles, and (emptied) ECR repos. If you only want to pause: EC2 → stop the instance (the Elastic IP then costs a little while the server is stopped).

---

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| Stack: `OIDCProvider … already exists` | Your account already has the GitHub provider. Delete the failed stack, recreate with **CreateGitHubOidcProvider = false**. |
| Stack: `InsufficientInstanceCapacity` / instance type not eligible | Re-create with the other of `t2.micro` / `t3.micro`. |
| Actions: `Could not assume role` / `Not authorized to perform sts:AssumeRoleWithWebIdentity` | The `AWS_ROLE_ARN` variable is wrong, or the repo name given in **GitHubRepo** doesn't exactly match `OWNER/NAME` (case-sensitive), or you pushed from a branch other than `main`. |
| Actions deploy: `InvalidInstanceId` / instance not in a valid state | Server's Systems Manager agent isn't Online yet. Wait a few minutes (Fleet Manager) and re-run the job. |
| Deploy log: `cd: /opt/webscout: No such file` | First-boot install still running. Check `/var/log/webscout-bootstrap.log`, wait, re-run. |
| Deploy log: `denied` / `no basic auth credentials` on pull | The `ECR_REGISTRY`/`AWS_REGION` lines in `/opt/webscout/.env` are wrong, or the first Actions build hasn't pushed images yet. |
| Site not loading on HTTPS | `docker compose logs caddy`. Let's Encrypt can rate-limit the shared `sslip.io` name; wait an hour, or set `EnableHttps=false` and use `http://IP`. |
| Server freezes / containers killed | `free -h`. Out of memory → move to `t3.small` (not free). |
| Backend log: Groq `model not found` | Edit `LLM_MODEL` in `/opt/webscout/.env` to a current model from https://console.groq.com/docs/models, then `docker compose up -d`. |
| Want to change the Groq key | Session Manager → `sudo nano /opt/webscout/.env` → `cd /opt/webscout && docker compose up -d`. |

## Security notes
- Your Groq key is entered as a (hidden) stack parameter and ends up in the server's `.env` (mode 600) **and** in the instance's first-boot script, which anyone with AWS access to your account can read. That's fine for a personal project. For something bigger use AWS Systems Manager Parameter Store.
- No SSH port is open. You use the browser shell (Session Manager) instead. Port 9000 / the old webhook is no longer used (`deploy/webhook_listener.py`, `ec2-setup.sh` are left in the repo for the manual route in the README but you can delete them).
- The app has no logins: anyone with the URL can spend your Groq quota (rate limit: 30 req/min/IP). For real use add authentication, or restrict ports 80/443 in the template to your own IP.
