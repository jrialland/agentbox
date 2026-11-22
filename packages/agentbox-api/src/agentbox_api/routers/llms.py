import pathlib

from fastapi import APIRouter, HTTPException, Response

router = APIRouter(tags=["docs"], include_in_schema=False)

_LLMS_DIR = pathlib.Path(__file__).resolve().parent.parent / "llms"


def _markdown(name: str) -> Response:
    try:
        text = (_LLMS_DIR / name).read_text(encoding="utf-8")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Not found") from None
    return Response(
        content=text,
        media_type="text/markdown; charset=utf-8",
        headers={"Cache-Control": "public, max-age=300"},
    )


SECTION_FILES = frozenset(
    {
        "authentication.md",
        "quickstart.md",
        "agents.md",
        "sessions.md",
        "streaming.md",
        "protocols.md",
        "reference.md",
    }
)


@router.get("/llms.txt")
async def llms_index() -> Response:
    return _markdown("llms.txt")


@router.get("/llms/{filename}")
async def llms_section(filename: str) -> Response:
    if filename not in SECTION_FILES:
        raise HTTPException(status_code=404, detail="Not found")
    return _markdown(filename)
