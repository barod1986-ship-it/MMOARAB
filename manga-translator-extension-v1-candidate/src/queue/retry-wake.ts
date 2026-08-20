import { browser } from 'wxt/browser';
import { MIN_DEFERRED_RETRY_MS, QUEUE_WAKE_ALARM } from '../shared/constants.js';

export class RetryWakeScheduler {
  async reconcile(notBeforeValues: readonly number[], now = Date.now()): Promise<number | null> {
    const future = notBeforeValues.filter((value) => Number.isFinite(value) && value > now).sort((a, b) => a - b);
    if (future.length === 0) {
      await browser.alarms.clear(QUEUE_WAKE_ALARM);
      return null;
    }
    const earliest = future[0]!;
    const when = Math.max(earliest, now + MIN_DEFERRED_RETRY_MS);
    const existing = await browser.alarms.get(QUEUE_WAKE_ALARM);
    if (!existing || Math.abs((existing.scheduledTime ?? 0) - when) > 1_000) {
      await browser.alarms.create(QUEUE_WAKE_ALARM, { when });
    }
    return when;
  }
}
