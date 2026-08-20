export type RemoteAuthority = 'active-tab-main-origin' | 'optional-exact-origin';

export type RemotePolicyInput = {
  candidateUrl: string;
  knownCandidateUrl?: string;
  sessionMainOrigin: string;
  finalResponseUrl?: string;
  exactOriginGranted: boolean;
  finalOriginGranted?: boolean;
};

export type RemotePolicyDecision =
  | { allowed: true; authority: RemoteAuthority; requestOrigin: string }
  | { allowed: false; reason: 'invalid-url' | 'candidate-mismatch' | 'permission-needed'; origin?: string };

export function evaluateRemotePolicy(input: RemotePolicyInput): RemotePolicyDecision {
  let candidate: URL;
  try {
    candidate = new URL(input.candidateUrl);
  } catch {
    return { allowed: false, reason: 'invalid-url' };
  }
  if (candidate.protocol !== 'https:' && candidate.origin !== input.sessionMainOrigin) {
    return { allowed: false, reason: 'invalid-url' };
  }
  if (input.knownCandidateUrl !== undefined && input.knownCandidateUrl !== candidate.href) {
    return { allowed: false, reason: 'candidate-mismatch' };
  }

  const isMainOrigin = candidate.origin === input.sessionMainOrigin;
  if (!isMainOrigin && !input.exactOriginGranted) {
    return { allowed: false, reason: 'permission-needed', origin: candidate.origin };
  }

  if (input.finalResponseUrl !== undefined) {
    let finalUrl: URL;
    try {
      finalUrl = new URL(input.finalResponseUrl);
    } catch {
      return { allowed: false, reason: 'invalid-url' };
    }
    const finalIsMainOrigin = finalUrl.origin === input.sessionMainOrigin;
    if (finalUrl.protocol !== 'https:' && !finalIsMainOrigin) {
      return { allowed: false, reason: 'invalid-url' };
    }
    if (finalUrl.origin !== candidate.origin) {
      if (!finalIsMainOrigin && !input.finalOriginGranted) {
        return { allowed: false, reason: 'permission-needed', origin: finalUrl.origin };
      }
      return {
        allowed: true,
        authority: finalIsMainOrigin ? 'active-tab-main-origin' : 'optional-exact-origin',
        requestOrigin: finalUrl.origin
      };
    }
  }

  return {
    allowed: true,
    authority: isMainOrigin ? 'active-tab-main-origin' : 'optional-exact-origin',
    requestOrigin: candidate.origin
  };
}

export function exactOriginPattern(origin: string): string | null {
  try {
    const url = new URL(origin);
    if (url.protocol !== 'https:') return null;
    return `${url.origin}/*`;
  } catch {
    return null;
  }
}
