import { sendMessage } from '../../messaging/protocol.js';
import type { AcquisitionOutcome, RectSnapshot, ViewportSnapshot } from '../types.js';

export async function acquireViaScreenshot(data: {
  sessionId: string;
  candidateId: string;
  rect: RectSnapshot;
  forPresentation: boolean;
}): Promise<AcquisitionOutcome> {
  const visual = window.visualViewport;
  const viewport: ViewportSnapshot = {
    width: visual?.width ?? window.innerWidth,
    height: visual?.height ?? window.innerHeight,
    visualOffsetLeft: visual?.offsetLeft ?? 0,
    visualOffsetTop: visual?.offsetTop ?? 0
  };
  return await sendMessage('background:capture-candidate', {
    sessionId: data.sessionId,
    candidateId: data.candidateId,
    rect: data.rect,
    viewport,
    forPresentation: data.forPresentation
  });
}
