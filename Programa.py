import threading


# ----------------------------
# Utilidades (sin usar otras librerías)
# ----------------------------

class LCG:
    """Pseudo-random simple (sin random)."""
    def __init__(self, seed: int):
        self.state = seed & 0x7fffffff

    def next(self) -> int:
        self.state = (1103515245 * self.state + 12345) & 0x7fffffff
        return self.state


def spin(n: int) -> None:
    """Pequeño trabajo ocupado para variar tiempos sin sleep/time."""
    x = 0
    for _ in range(n):
        x ^= (x << 1) & 0xFFFFFFFF


# ----------------------------
# Lock estilo Lamport Bakery (sin Lock/Semaphore/Condition de threading)
# ----------------------------

class BakeryLock:
    """
    Lamport's Bakery Algorithm para exclusión mutua entre N hilos.
    Requiere que cada hilo tenga un id único en [0, N-1].
    """
    def __init__(self, n: int):
        self.n = n
        self.choosing = [False] * n
        self.number = [0] * n

    def acquire(self, tid: int) -> None:
        self.choosing[tid] = True

        # number[tid] = 1 + max(number)
        maxnum = 0
        for v in self.number:
            if v > maxnum:
                maxnum = v
        self.number[tid] = maxnum + 1

        self.choosing[tid] = False

        for j in range(self.n):
            if j == tid:
                continue

            while self.choosing[j]:
                pass

            while self.number[j] != 0:
                nj = self.number[j]
                ni = self.number[tid]
                if nj < ni or (nj == ni and j < tid):
                    continue
                break

    def release(self, tid: int) -> None:
        self.number[tid] = 0


class Semaphore:
    """Semáforo construido encima de BakeryLock (sin threading.Semaphore)."""
    def __init__(self, initial: int, nthreads: int):
        if initial < 0:
            raise ValueError("Semaphore initial must be >= 0")
        self.value = initial
        self.mutex = BakeryLock(nthreads)

    def wait(self, tid: int) -> None:
        while True:
            self.mutex.acquire(tid)
            if self.value > 0:
                self.value -= 1
                self.mutex.release(tid)
                return
            self.mutex.release(tid)
            # Spin pequeño para no quemar 100% en el mismo punto siempre
            spin(200)

    def signal(self, tid: int) -> None:
        self.mutex.acquire(tid)
        self.value += 1
        self.mutex.release(tid)


# ----------------------------
# Readers-Writers con PRIORIDAD a ESCRITORES
# ----------------------------

class RWWriterPriority:
    def __init__(self, nthreads: int):
        # Semáforos del algoritmo clásico de prioridad escritores
        self.resource = Semaphore(1, nthreads)   # controla acceso al recurso compartido
        self.rmutex = Semaphore(1, nthreads)     # protege read_count
        self.wmutex = Semaphore(1, nthreads)     # protege write_count
        self.readTry = Semaphore(1, nthreads)    # bloquea lectores si hay escritores esperando

        self.read_count = 0
        self.write_count = 0

        # Solo para logs/validación (no es parte del algoritmo)
        self.print_mutex = Semaphore(1, nthreads)
        self.state_mutex = Semaphore(1, nthreads)
        self.active_readers = 0
        self.active_writers = 0

        self.shared_value = 0

    def log(self, tid: int, msg: str) -> None:
        self.print_mutex.wait(tid)
        print(msg)
        self.print_mutex.signal(tid)

    def reader_enter(self, tid: int) -> None:
        self.readTry.wait(tid)
        self.rmutex.wait(tid)

        self.read_count += 1
        if self.read_count == 1:
            self.resource.wait(tid)

        self.rmutex.signal(tid)
        self.readTry.signal(tid)

    def reader_exit(self, tid: int) -> None:
        self.rmutex.wait(tid)

        self.read_count -= 1
        if self.read_count == 0:
            self.resource.signal(tid)

        self.rmutex.signal(tid)

    def writer_enter(self, tid: int) -> None:
        self.wmutex.wait(tid)

        self.write_count += 1
        if self.write_count == 1:
            self.readTry.wait(tid)

        self.wmutex.signal(tid)

        self.resource.wait(tid)

    def writer_exit(self, tid: int) -> None:
        self.resource.signal(tid)

        self.wmutex.wait(tid)

        self.write_count -= 1
        if self.write_count == 0:
            self.readTry.signal(tid)

        self.wmutex.signal(tid)

    # Helpers para validar (opcional)
    def begin_read_cs(self, tid: int) -> None:
        self.state_mutex.wait(tid)
        self.active_readers += 1
        # En prioridad escritores, nunca debe haber escritor activo mientras se lee
        if self.active_writers != 0:
            self.log(tid, f"[ERROR] Lector {tid}: active_writers={self.active_writers} != 0")
        self.state_mutex.signal(tid)

    def end_read_cs(self, tid: int) -> None:
        self.state_mutex.wait(tid)
        self.active_readers -= 1
        self.state_mutex.signal(tid)

    def begin_write_cs(self, tid: int) -> None:
        self.state_mutex.wait(tid)
        self.active_writers += 1
        # Nunca debe haber lectores/escritores simultáneos con un escritor
        if self.active_writers != 1 or self.active_readers != 0:
            self.log(tid, f"[ERROR] Escritor {tid}: active_writers={self.active_writers}, active_readers={self.active_readers}")
        self.state_mutex.signal(tid)

    def end_write_cs(self, tid: int) -> None:
        self.state_mutex.wait(tid)
        self.active_writers -= 1
        self.state_mutex.signal(tid)


def run_timer(stop_event: threading.Event, seconds: int) -> None:
    stop_event.wait(seconds)   # usa SOLO threading para temporizar
    stop_event.set()


def reader_thread(tid: int, rw: RWWriterPriority, stop_event: threading.Event, stats: list[int]) -> None:
    prng = LCG(1234567 + tid * 101)

    it = 0
    while not stop_event.is_set():
        # Intentar entrar
        rw.reader_enter(tid)

        # Sección crítica (lectura)
        rw.begin_read_cs(tid)
        value = rw.shared_value
        rw.log(tid, f"[R{tid}] >>> ENTRA  CS (iter={it}) lee={value}")
        spin(1000 + (prng.next() % 2000))
        rw.log(tid, f"[R{tid}] <<< SALE   CS (iter={it}) lee={value}")
        rw.end_read_cs(tid)

        rw.reader_exit(tid)

        stats[tid] += 1
        it += 1
        spin(800 + (prng.next() % 2500))


def writer_thread(tid: int, rw: RWWriterPriority, stop_event: threading.Event, stats: list[int]) -> None:
    prng = LCG(7654321 + tid * 313)

    it = 0
    while not stop_event.is_set():
        rw.writer_enter(tid)

        # Sección crítica (escritura)
        rw.begin_write_cs(tid)
        before = rw.shared_value
        rw.log(tid, f"[W{tid}] >>> ENTRA  CS (iter={it}) antes={before}")
        spin(2000 + (prng.next() % 3500))
        rw.shared_value = before + 1
        after = rw.shared_value
        rw.log(tid, f"[W{tid}] <<< SALE   CS (iter={it}) despues={after}")
        rw.end_write_cs(tid)

        rw.writer_exit(tid)

        stats[tid] += 1
        it += 1
        spin(1200 + (prng.next() % 4000))


def main() -> None:
    # Configurable (puedes cambiar aquí)
    NUM_READERS = 5
    NUM_WRITERS = 3
    DURATION_SECONDS = 60  # mínimo 60

    if DURATION_SECONDS < 60:
        DURATION_SECONDS = 60

    nthreads = NUM_READERS + NUM_WRITERS
    rw = RWWriterPriority(nthreads)

    stop_event = threading.Event()
    stats = [0] * nthreads

    threads: list[threading.Thread] = []

    # Crear lectores (tid 0..NUM_READERS-1)
    for i in range(NUM_READERS):
        t = threading.Thread(target=reader_thread, args=(i, rw, stop_event, stats), name=f"Reader-{i}")
        threads.append(t)

    # Crear escritores (tid NUM_READERS..nthreads-1)
    for k in range(NUM_WRITERS):
        tid = NUM_READERS + k
        t = threading.Thread(target=writer_thread, args=(tid, rw, stop_event, stats), name=f"Writer-{tid}")
        threads.append(t)

    timer = threading.Thread(target=run_timer, args=(stop_event, DURATION_SECONDS), name="Timer")

    # Iniciar
    for t in threads:
        t.start()
    timer.start()

    # Esperar fin
    timer.join()
    for t in threads:
        t.join()

    # Resumen
    total_reads = 0
    total_writes = 0
    for tid in range(nthreads):
        if tid < NUM_READERS:
            total_reads += stats[tid]
        else:
            total_writes += stats[tid]

    print("\n=== RESUMEN ===")
    print(f"Lectores: {NUM_READERS} | Escritores: {NUM_WRITERS} | Duración: {DURATION_SECONDS}s")
    print(f"Operaciones lectura:  {total_reads}")
    print(f"Operaciones escritura:{total_writes}")
    print(f"Valor final compartido: {rw.shared_value}")


if __name__ == "__main__":
    main()