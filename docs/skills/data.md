# Data Version Control (DVC) Skill

Float uses DVC to version datasets, raw knowledge documents, evaluation sets, and machine learning artifacts without storing large binary or content files in Git.

## Golden Rules
1. **Data Never Goes into Git**: Raw knowledge (`data/knowledge/**`), evaluation datasets (`evals/data/**`), embeddings, ML models, and raw datasets are tracked by DVC only.
2. **Git Tracks Pointers**: Git tracks only `.dvc` pointer files (`*.dvc`), `dvc.lock`, `dvc.yaml`, the SHA-256 test manifests (`manifest.sha256`), and tiny test fixtures under `tests/fixtures/`.
3. **Local Remote Outside Repo**: Default local remote (`D:\float-dvc-remote`) is configured in `.dvc/config.local` (gitignored). Committed config (`.dvc/config`) never stores credentials or machine-specific local paths.
4. **CI Parity**: CI runs without `dvc pull` and must pass using static test fixtures.

---

## Daily Operations

### 1. Tracking Data
```bash
python -m dvc add data/knowledge
git add data/knowledge.dvc .gitignore
```

### 2. Pushing Data to Remote
```bash
python -m dvc push
```

### 3. Pulling Data on a Fresh Machine
```bash
# Configure local remote if not present in .dvc/config.local:
python -m dvc remote add -d --local local_storage D:\float-dvc-remote
# Pull data
python -m dvc pull
```

### 4. Reproducing Pipelines
```bash
python -m dvc repro
```

---

## Switching Remotes

### S3 (AWS / MinIO)
```bash
python -m dvc remote add -d --local s3_storage s3://my-float-bucket/dvc
python -m dvc remote modify --local s3_storage access_key_id <KEY>
python -m dvc remote modify --local s3_storage secret_access_key <SECRET>
```

### Google Drive
```bash
python -m dvc remote add -d --local gdrive_storage gdrive://<FOLDER_ID>
```

### DagsHub
```bash
python -m dvc remote add -d --local dagshub https://dagshub.com/<user>/float.dvc
python -m dvc remote modify --local dagshub --user <user> --password <token>
```

---

## Recovery Note
If raw data was accidentally staged or tracked in Git:
```bash
# 1. Unstage/untrack without deleting local file:
git rm --cached -r data/knowledge/
# 2. Add to DVC:
python -m dvc add data/knowledge
# 3. Add pointer to Git:
git add data/knowledge.dvc .gitignore
git commit -m "chore(data): track data/knowledge with DVC"
```
If a file was already committed to Git in past commits:
- Do NOT rewrite published Git history (`git filter-repo` / `git rebase`).
- Remove from HEAD with `git rm --cached`, commit the removal, and track via DVC.
- If proprietary or sensitive data was committed, coordinate with the repository owner to purge history on a maintenance window.

> [!NOTE]
> `python -m dvc pull` will not work until a remote is added in `.dvc/config.local` (see **Switching Remotes** above).

---

## Branch Merge-Order & CI Parity Rule
- **Merge Order**: `feature/backend-auth` → `feature/web-app` → `feature/admin-panel` (already in `origin/develop` via PR #29) → `feature/ai-literacy-dvc`.
- Before pushing each branch:
  1. Update from the latest `origin/develop` using `git merge origin/develop` (not rebase).
  2. Keep Alembic migrations as a **single linear head** (repoint the later migration's `down_revision` to the current head).
  3. Run `scripts\ci_local.cmd` (and `npm test` + `npm run build` for `feature/web-app`).
