from pathlib import Path


def resolve_local_version(source):
    path = Path(source)
    return {
        "source": str(path),
        "version": "local",
    }


def resolve_github_release_reference(reference):
    repo = reference.get("repo", "")
    version = reference.get("version", reference.get("tag", ""))

    return {
        "source": f"github:{repo}",
        "version": version or "unresolved-release",
        "github_release": {
            "repo": repo,
            "version": version,
            "stub": True,
        },
    }

