import time
import functools
import platform

# =========================================================
# READ DRAM ENERGY FROM RAPL (Linux only)
# =========================================================
def read_dram_joules():

    if platform.system() != "Linux":
        return None

    path = (
        "/sys/class/powercap/intel-rapl/"
        "intel-rapl:0/intel-rapl:0:2/energy_uj"
    )

    try:
        with open(path, "r") as f:
            return int(f.read().strip()) / 1_000_000.0

    except (FileNotFoundError, OSError):
        return None


# =========================================================
# READ RAM USAGE VIA PSUTIL (cross-platform fallback)
# =========================================================
def read_ram_mb():
    try:
        import psutil
        return psutil.Process().memory_info().rss / 1024 / 1024  # MB
    except ImportError:
        return None


# =========================================================
# DECORATOR FOR RAM ENERGY PROFILING
# =========================================================
def measure_ram_energy(func):

    @functools.wraps(func)
    def wrapper(*args, **kwargs):

        print(f"\n[RAM PROFILER] Running: {func.__name__}")

        # -----------------------------------------
        # START MEASUREMENT
        # -----------------------------------------
        start_energy = read_dram_joules()
        start_ram    = read_ram_mb()
        start_time   = time.time()

        # -----------------------------------------
        # RUN FUNCTION
        # -----------------------------------------
        result = func(*args, **kwargs)

        # -----------------------------------------
        # END MEASUREMENT
        # -----------------------------------------
        end_energy = read_dram_joules()
        end_ram    = read_ram_mb()
        end_time   = time.time()

        duration = end_time - start_time

        # -----------------------------------------
        # REPORT
        # -----------------------------------------
        print("\n========== RAM ENERGY REPORT ==========")
        print(f"Function       : {func.__name__}")
        print(f"Execution Time : {duration:.4f} sec")

        if start_energy is not None and end_energy is not None:
            total_energy  = end_energy - start_energy
            average_power = total_energy / duration if duration > 0 else 0
            print(f"DRAM Energy    : {total_energy:.6f} Joules")
            print(f"Average Power  : {average_power:.6f} Watts")
        else:
            print("DRAM Energy    : N/A (RAPL not available on Windows)")

        if start_ram is not None and end_ram is not None:
            print(f"RAM Start      : {start_ram:.2f} MB")
            print(f"RAM End        : {end_ram:.2f} MB")
            print(f"RAM Delta      : {end_ram - start_ram:+.2f} MB")
        else:
            print("RAM Usage      : N/A (install psutil: pip install psutil)")

        print("=======================================\n")

        return result

    return wrapper