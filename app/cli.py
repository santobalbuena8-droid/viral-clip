"""Ejecuta un job en primer plano.

Ejemplos:
  python -m app.cli --local data/fixtures/sample_60s.mp4 --max-clips 2
  python -m app.cli --url https://www.youtube.com/watch?v=jNQXAC9IVRw
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.models import JobStatus
from app.pipeline.jobs import create_job, run_job


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(
        prog="viral-clip",
        description="Viral Clip: descarga, elige momentos y exporta clips 9:16.",
    )
    parser.add_argument("--url", help="URL http(s) de YouTube")
    parser.add_argument("--local", help="Ruta a un video en esta máquina")
    parser.add_argument("--max-clips", type=int, default=3)
    args = parser.parse_args(argv)

    if args.local:
        source = str(Path(args.local).expanduser().resolve())
    elif args.url:
        source = args.url.strip()
    else:
        parser.error("indica --url o --local")
    if not 1 <= args.max_clips <= 5:
        parser.error("--max-clips tiene que estar entre 1 y 5")

    job = create_job(source, args.max_clips)
    print(f"job {job.id} en cola", file=sys.stderr, flush=True)
    finished = run_job(job.id)
    print(finished.model_dump_json(indent=2))
    return 0 if finished.status == JobStatus.completed else 1


if __name__ == "__main__":
    sys.exit(main())
