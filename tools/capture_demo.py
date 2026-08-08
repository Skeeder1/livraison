#!/usr/bin/env python3
"""
Capture la démonstration animée des tournées : images fixes + vidéo.

Le rendu `vrp_visualization.html` est une carte Leaflet animée par un curseur
temporel. Ce script pilote ce curseur image par image dans un navigateur sans
interface, capture chaque état, puis assemble le tout avec ffmpeg.

Pourquoi piloter le curseur plutôt qu'enregistrer le bouton « Play » :
la capture devient **déterministe** — un nombre d'images fixe, régulièrement
réparti sur la durée simulée — au lieu de dépendre de la cadence d'animation et
de la charge machine.

Usage :
    python tools/capture_demo.py [--frames 240] [--fps 24]

Prérequis : le HTML doit avoir été généré (`python -m optimizer.main`) et ffmpeg
doit être installé.
"""
from __future__ import annotations

import argparse
import functools
import glob
import http.server
import os
import shutil
import socketserver
import subprocess
import sys
import threading

from playwright.sync_api import sync_playwright

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HTML_NAME = "vrp_visualization.html"
FRAMES_DIR = os.path.join(REPO_ROOT, "docs", "images", "_frames")
OUTPUT_DIR = os.path.join(REPO_ROOT, "docs", "images")
PORT = 8799


def find_chromium():
    """
    Localise un Chromium déjà présent dans le cache Playwright.

    Playwright épingle un numéro de build précis et refuse de démarrer si le
    cache contient une autre version. Plutôt que de retélécharger ~150 Mo, on
    réutilise le binaire disponible.
    """
    pattern = os.path.expanduser("~/.cache/ms-playwright/chromium-*/chrome-linux64/chrome")
    candidates = sorted(glob.glob(pattern))
    if not candidates:
        return None
    return candidates[-1]


def serve_repo():
    """Sert le dépôt en HTTP local : le protocole file:// est refusé par Chromium."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=REPO_ROOT)
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.TCPServer(("127.0.0.1", PORT), handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def capture(frames: int, width: int, height: int):
    if not os.path.exists(os.path.join(REPO_ROOT, HTML_NAME)):
        sys.exit(f"{HTML_NAME} introuvable. Lancez d'abord : python -m optimizer.main")

    shutil.rmtree(FRAMES_DIR, ignore_errors=True)
    os.makedirs(FRAMES_DIR, exist_ok=True)

    httpd = serve_repo()
    chromium_path = find_chromium()

    try:
        with sync_playwright() as p:
            launch_args = {"args": ["--force-device-scale-factor=1"]}
            if chromium_path:
                launch_args["executable_path"] = chromium_path
            browser = p.chromium.launch(**launch_args)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"http://127.0.0.1:{PORT}/{HTML_NAME}", wait_until="networkidle")

            # Laisser les tuiles OpenStreetMap se charger avant la première image.
            page.wait_for_timeout(4000)

            max_time = int(page.evaluate("() => document.getElementById('time-slider').max"))
            print(f"Durée simulée : {max_time} s — {frames} images à capturer")

            for i in range(frames):
                t = int(max_time * i / max(1, frames - 1))
                page.evaluate(
                    """(value) => {
                        const slider = document.getElementById('time-slider');
                        slider.value = value;
                        slider.dispatchEvent(new Event('input', { bubbles: true }));
                    }""",
                    t,
                )
                # Laisser Leaflet repositionner les marqueurs avant la capture.
                page.wait_for_timeout(60)
                page.screenshot(path=os.path.join(FRAMES_DIR, f"frame_{i:04d}.png"))
                if i % 40 == 0:
                    print(f"  image {i}/{frames} (t = {t} s)")

            browser.close()
    finally:
        httpd.shutdown()

    print(f"{frames} images capturées dans {FRAMES_DIR}")


def encode(fps: int):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pattern = os.path.join(FRAMES_DIR, "frame_%04d.png")
    mp4_path = os.path.join(OUTPUT_DIR, "demo-tournees.mp4")
    gif_path = os.path.join(OUTPUT_DIR, "demo-tournees.gif")

    subprocess.run(
        ["ffmpeg", "-y", "-framerate", str(fps), "-i", pattern,
         # yuv420p + dimensions paires : indispensable pour une lecture correcte
         # dans les navigateurs et sur GitHub.
         "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
         mp4_path],
        check=True, capture_output=True,
    )

    # GIF : palette dédiée, sinon le dégradé des tuiles part en banding.
    palette = os.path.join(FRAMES_DIR, "palette.png")
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp4_path, "-vf", "fps=12,scale=900:-1:flags=lanczos,palettegen",
         palette], check=True, capture_output=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", mp4_path, "-i", palette,
         "-lavfi", "fps=12,scale=900:-1:flags=lanczos[x];[x][1:v]paletteuse",
         gif_path], check=True, capture_output=True,
    )

    for path in (mp4_path, gif_path):
        print(f"{path} — {os.path.getsize(path) / 1024:.0f} Ko")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=240, help="Nombre d'images à capturer")
    parser.add_argument("--fps", type=int, default=24, help="Images par seconde de la vidéo")
    parser.add_argument("--width", type=int, default=1440)
    parser.add_argument("--height", type=int, default=900)
    args = parser.parse_args()

    capture(args.frames, args.width, args.height)
    encode(args.fps)


if __name__ == "__main__":
    main()
