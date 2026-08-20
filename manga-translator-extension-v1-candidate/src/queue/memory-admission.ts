import { MEMORY_SOFT_BUDGET_BYTES, UNKNOWN_BINARY_RESERVATION_BYTES } from '../shared/constants.js';

export type MemoryReservation = { bytes: number; exclusive: boolean; release(): void };

export class MemoryAdmissionController {
  readonly budgetBytes: number;
  #reservedBytes = 0;
  #waiters: Array<() => void> = [];

  constructor(budgetBytes = MEMORY_SOFT_BUDGET_BYTES) {
    this.budgetBytes = budgetBytes;
  }

  get reservedBytes(): number {
    return this.#reservedBytes;
  }

  async reserve(requestedBytes?: number): Promise<MemoryReservation> {
    const bytes = sanitizeEstimate(requestedBytes);
    const exclusive = bytes > this.budgetBytes;
    while (!this.#canReserve(bytes, exclusive)) {
      await new Promise<void>((resolve) => this.#waiters.push(resolve));
    }
    this.#reservedBytes += bytes;
    let released = false;
    return {
      bytes,
      exclusive,
      release: () => {
        if (released) return;
        released = true;
        this.#reservedBytes = Math.max(0, this.#reservedBytes - bytes);
        const waiters = this.#waiters.splice(0);
        for (const wake of waiters) wake();
      }
    };
  }

  #canReserve(bytes: number, exclusive: boolean): boolean {
    if (exclusive) return this.#reservedBytes === 0;
    return this.#reservedBytes + bytes <= this.budgetBytes;
  }
}

export function sanitizeEstimate(value?: number): number {
  if (value === undefined || !Number.isFinite(value) || value <= 0) return UNKNOWN_BINARY_RESERVATION_BYTES;
  return Math.ceil(value);
}
