# ============================================================================
# IDM Test - Benchmark Module
# Disk sequential read/write speed + GPU rendering FPS
# Dependencies: pygame (untuk GPU FPS)
# ============================================================================

import os
import sys
import time
import tempfile
import threading
from dataclasses import dataclass
from typing import Optional

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False

try:
    import wmi as wmi_module
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False


@dataclass
class BenchmarkResult:
    disk_read_mbps: Optional[float] = None
    disk_write_mbps: Optional[float] = None
    gpu_name: str = "N/A"
    gpu_vram_mb: Optional[int] = None
    gpu_driver: str = "N/A"
    gpu_fps_avg: Optional[float] = None
    gpu_fps_min: Optional[float] = None


# ══════════════════════════════════════════════════════════════════════════
#  GPU Info via WMI
# ══════════════════════════════════════════════════════════════════════════

def get_gpu_info() -> dict:
    info = {"name": "N/A", "vram_mb": None, "driver": "N/A"}
    if not WMI_AVAILABLE:
        return info
    try:
        w = wmi_module.WMI()
        for gpu in w.Win32_VideoController():
            name = gpu.Name or ""
            if name:
                info["name"] = name
                vram = getattr(gpu, "AdapterRAM", None)
                if vram and int(vram) > 0:
                    info["vram_mb"] = int(vram) // (1024 * 1024)
                info["driver"] = getattr(gpu, "DriverVersion", "N/A") or "N/A"
                break
    except Exception:
        pass
    return info


# ══════════════════════════════════════════════════════════════════════════
#  Disk Sequential Read/Write Benchmark
# ══════════════════════════════════════════════════════════════════════════

def disk_benchmark(
    size_mb: int = 128,
    block_kb: int = 1024,
    on_progress=None,
) -> tuple[Optional[float], Optional[float]]:
    """
    Sequential write then read benchmark.
    Returns (read_MB/s, write_MB/s).
    """
    block = os.urandom(block_kb * 1024)
    blocks = (size_mb * 1024) // block_kb
    test_path = os.path.join(tempfile.gettempdir(), "idm_disk_bench.tmp")

    write_speed = None
    read_speed = None

    try:
        # ── Write test ──
        if on_progress:
            on_progress("tulis")
        start = time.perf_counter()
        with open(test_path, "wb") as f:
            for _ in range(blocks):
                f.write(block)
            f.flush()
            os.fsync(f.fileno())
        elapsed = time.perf_counter() - start
        if elapsed > 0:
            write_speed = round(size_mb / elapsed, 1)

        # ── Read test ──
        if on_progress:
            on_progress("baca")
        start = time.perf_counter()
        with open(test_path, "rb") as f:
            while f.read(block_kb * 1024):
                pass
        elapsed = time.perf_counter() - start
        if elapsed > 0:
            read_speed = round(size_mb / elapsed, 1)
    except Exception:
        pass
    finally:
        try:
            os.remove(test_path)
        except Exception:
            pass

    return read_speed, write_speed


# ══════════════════════════════════════════════════════════════════════════
#  GPU Rendering FPS Benchmark (pygame)
# ══════════════════════════════════════════════════════════════════════════

import math
import random


def _run_gpu_bench(duration_sec: int, result_holder: dict):
    """Pygame rendering loop — runs in its own thread on Windows."""
    if not PYGAME_AVAILABLE:
        return

    try:
        pygame.init()
        W, H = 800, 600
        screen = pygame.display.set_mode((W, H), pygame.HWSURFACE | pygame.DOUBLEBUF)
        pygame.display.set_caption("IDM Test — Benchmark GPU")
        clock = pygame.time.Clock()

        font_big = pygame.font.SysFont("Segoe UI", 28, bold=True)
        font_sm = pygame.font.SysFont("Segoe UI", 16)
        font_fps = pygame.font.SysFont("Consolas", 40, bold=True)

        particles = []
        for _ in range(300):
            particles.append([
                random.uniform(0, W), random.uniform(0, H),
                random.uniform(-2, 2), random.uniform(-2, 2),
                random.randint(2, 6),
                (random.randint(100, 255), random.randint(50, 200),
                 random.randint(50, 200)),
            ])

        frame_count = 0
        fps_list = []
        t_start = time.perf_counter()
        running = True

        while running and (time.perf_counter() - t_start) < duration_sec:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            elapsed = time.perf_counter() - t_start
            t = elapsed * 2

            screen.fill((20, 20, 40))

            for i in range(12):
                angle = t + i * (math.pi * 2 / 12)
                cx = W // 2 + math.cos(angle) * 180
                cy = H // 2 + math.sin(angle) * 180
                size = 30 + math.sin(t * 1.5 + i) * 15
                r = int(120 + 100 * math.sin(t + i))
                g = int(80 + 80 * math.cos(t * 0.7 + i))
                b = int(180 + 60 * math.sin(t * 1.3 + i))
                color = (max(0, min(255, r)), max(0, min(255, g)),
                         max(0, min(255, b)))

                points = []
                for v in range(6):
                    a = angle + v * (math.pi * 2 / 6) + t * 0.5
                    px = cx + math.cos(a) * size
                    py = cy + math.sin(a) * size
                    points.append((px, py))
                pygame.draw.polygon(screen, color, points, 0)
                pygame.draw.polygon(screen, (255, 255, 255), points, 1)

            for p in particles:
                p[0] = (p[0] + p[2]) % W
                p[1] = (p[1] + p[3]) % H
                pygame.draw.circle(screen, p[5], (int(p[0]), int(p[1])), p[4])

            for i in range(20):
                x = int(W / 2 + math.cos(t * 3 + i * 0.5) * (100 + i * 10))
                y = int(H / 2 + math.sin(t * 2 + i * 0.7) * (80 + i * 8))
                rad = 8 + int(math.sin(t * 4 + i) * 5)
                alpha = max(60, 200 - i * 8)
                pygame.draw.circle(screen, (233, 69, 96, alpha),
                                   (x, y), rad)

            current_fps = clock.get_fps()
            if frame_count > 5:
                fps_list.append(current_fps)

            title_surf = font_big.render("IDM Test — Benchmark GPU",
                                          True, (233, 69, 96))
            screen.blit(title_surf, (W // 2 - title_surf.get_width() // 2, 20))

            remaining = max(0, duration_sec - elapsed)
            info_text = f"Sisa waktu: {int(remaining)}d"
            info_surf = font_sm.render(info_text, True, (180, 180, 180))
            screen.blit(info_surf, (W // 2 - info_surf.get_width() // 2, 56))

            fps_text = f"{current_fps:.0f} FPS"
            fps_surf = font_fps.render(fps_text, True, (0, 200, 83))
            screen.blit(fps_surf,
                        (W // 2 - fps_surf.get_width() // 2,
                         H // 2 - fps_surf.get_height() // 2))

            progress_w = int((elapsed / duration_sec) * (W - 40))
            pygame.draw.rect(screen, (30, 30, 60), (20, H - 30, W - 40, 12))
            pygame.draw.rect(screen, (233, 69, 96), (20, H - 30,
                                                       progress_w, 12))

            pygame.display.flip()
            clock.tick(0)
            frame_count += 1

        pygame.quit()

        if fps_list:
            result_holder["avg"] = round(sum(fps_list) / len(fps_list), 1)
            result_holder["min"] = round(min(fps_list), 1)
        result_holder["frames"] = frame_count
    except Exception as exc:
        result_holder["error"] = str(exc)
    finally:
        try:
            pygame.quit()
        except Exception:
            pass


def gpu_benchmark(duration_sec: int = 10) -> tuple[Optional[float],
                                                     Optional[float]]:
    """
    Run GPU rendering benchmark.
    Returns (avg_fps, min_fps).
    """
    if not PYGAME_AVAILABLE:
        return None, None

    result = {}
    t = threading.Thread(target=_run_gpu_bench,
                         args=(duration_sec, result), daemon=True)
    t.start()
    t.join(timeout=duration_sec + 10)

    return result.get("avg"), result.get("min")


# ══════════════════════════════════════════════════════════════════════════
#  Full Benchmark Suite
# ══════════════════════════════════════════════════════════════════════════

def run_full_benchmark(
    disk_size_mb: int = 128,
    gpu_duration_sec: int = 10,
    on_phase=None,
) -> BenchmarkResult:
    result = BenchmarkResult()

    gpu_info = get_gpu_info()
    result.gpu_name = gpu_info["name"]
    result.gpu_vram_mb = gpu_info["vram_mb"]
    result.gpu_driver = gpu_info["driver"]

    if on_phase:
        on_phase("disk")
    read_s, write_s = disk_benchmark(disk_size_mb)
    result.disk_read_mbps = read_s
    result.disk_write_mbps = write_s

    if on_phase:
        on_phase("gpu")
    avg_fps, min_fps = gpu_benchmark(gpu_duration_sec)
    result.gpu_fps_avg = avg_fps
    result.gpu_fps_min = min_fps

    return result
