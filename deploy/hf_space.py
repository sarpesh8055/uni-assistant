"""Deploy to a Hugging Face Space (Docker SDK).

Run:  python -m deploy.hf_space [--space USER/NAME] [--private]
Needs HF_TOKEN (write access) and LLM_API_KEY in .env.

- Creates the Space if it doesn't exist
- Uploads the code (never .env, PDFs or local indexes; the image builds its own index)
- Stores LLM_API_KEY as an encrypted Space *secret*, other settings as Space *variables*
"""
import argparse
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent.parent
UPLOAD = ["Dockerfile", "start.sh", "requirements.txt", ".dockerignore", "src/*.py"]
VARIABLES = ["LLM_BASE_URL", "LLM_MODEL", "JUDGE_MODEL", "FAITHFULNESS_CHECK", "MIN_DENSE_SCORE", "EMBED_MODEL"]

SPACE_HEADER = """---
title: Uni Paderborn Study Assistant
emoji: 🎓
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Bilingual RAG assistant for exam regulations, with citations
---

"""


def main():
    from huggingface_hub import HfApi

    env = dotenv_values(ROOT / ".env")
    token = env.get("HF_TOKEN")
    if not token:
        raise SystemExit("HF_TOKEN missing in .env")
    if not env.get("LLM_API_KEY"):
        raise SystemExit("LLM_API_KEY missing in .env")

    api = HfApi(token=token)
    user = api.whoami()["name"]
    p = argparse.ArgumentParser()
    p.add_argument("--space", default=f"{user}/uni-assistant")
    p.add_argument("--private", action="store_true")
    args = p.parse_args()

    api.create_repo(args.space, repo_type="space", space_sdk="docker", private=args.private, exist_ok=True)
    print(f"✓ Space ready: {args.space}")

    # settings first, so the first build already has them
    api.add_space_secret(args.space, "LLM_API_KEY", env["LLM_API_KEY"])
    print("✓ secret LLM_API_KEY set (encrypted on Hugging Face, not in the code)")
    for name in VARIABLES:
        if env.get(name):
            api.add_space_variable(args.space, name, env[name])
            print(f"✓ variable {name}={env[name]}")

    readme = SPACE_HEADER + (ROOT / "README.md").read_text(encoding="utf-8")
    api.upload_file(path_or_fileobj=readme.encode("utf-8"), path_in_repo="README.md",
                    repo_id=args.space, repo_type="space", commit_message="Update README")
    api.upload_folder(folder_path=str(ROOT), repo_id=args.space, repo_type="space",
                      allow_patterns=UPLOAD, commit_message="Deploy from local repo")
    print(f"✓ code uploaded. Build log: https://huggingface.co/spaces/{args.space}?logs=build")
    print(f"  App URL (after the build, ~10 min): https://huggingface.co/spaces/{args.space}")


if __name__ == "__main__":
    main()
