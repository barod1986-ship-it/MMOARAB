export class AsyncLane {
  readonly capacity: number;
  #active = 0;
  #waiters: Array<() => void> = [];

  constructor(capacity: number) {
    if (!Number.isInteger(capacity) || capacity < 1) throw new Error('Lane capacity must be a positive integer.');
    this.capacity = capacity;
  }

  get active(): number {
    return this.#active;
  }

  async run<T>(operation: () => Promise<T>): Promise<T> {
    await this.#enter();
    try {
      return await operation();
    } finally {
      this.#leave();
    }
  }

  async #enter(): Promise<void> {
    if (this.#active < this.capacity) {
      this.#active += 1;
      return;
    }
    await new Promise<void>((resolve) => this.#waiters.push(resolve));
    this.#active += 1;
  }

  #leave(): void {
    this.#active = Math.max(0, this.#active - 1);
    this.#waiters.shift()?.();
  }
}
