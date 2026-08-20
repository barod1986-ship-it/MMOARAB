export type CandidateScoreInput = {
  viewportWidth: number;
  viewportHeight: number;
  rect: { x: number; y: number; width: number; height: number };
  naturalWidth?: number;
  naturalHeight?: number;
  visible: boolean;
  hidden: boolean;
  insideChromeUi: boolean;
  insideSemanticUi: boolean;
  likelyTrackingPixel: boolean;
  extensionOwned: boolean;
  sourceUrl?: string;
};

export function scoreCandidate(input: CandidateScoreInput): number {
  if (input.extensionOwned || input.hidden || input.likelyTrackingPixel) return 0;
  const viewportArea = Math.max(1, input.viewportWidth * input.viewportHeight);
  const area = Math.max(0, input.rect.width * input.rect.height);
  const areaRatio = Math.min(2, area / viewportArea);
  const widthRatio = Math.min(1.5, input.rect.width / Math.max(1, input.viewportWidth));

  let score = 0.08;
  score += Math.min(0.32, areaRatio * 0.34);
  score += Math.min(0.24, widthRatio * 0.24);

  const naturalArea = (input.naturalWidth ?? 0) * (input.naturalHeight ?? 0);
  if (naturalArea >= 500_000) score += 0.14;
  else if (naturalArea >= 150_000) score += 0.08;

  if (input.visible) score += 0.1;
  if (input.insideChromeUi) score -= 0.22;
  if (input.insideSemanticUi) score -= 0.15;

  if (input.rect.width < 80 || input.rect.height < 80) score -= 0.2;
  if (input.sourceUrl && /(?:avatar|icon|logo|sprite|thumb)/i.test(input.sourceUrl)) score -= 0.08;
  if (input.sourceUrl && /(?:page|chapter|comic|manga|webtoon|image|img)/i.test(input.sourceUrl)) score += 0.04;

  return clamp01(score);
}

export type GroupMember = {
  id: string;
  parentKey: string;
  sourceFamily: string;
  centerX: number;
  width: number;
  top: number;
  bottom: number;
  baseScore: number;
};

export function applyGroupBoost(members: GroupMember[]): Map<string, number> {
  const result = new Map<string, number>();
  const byParent = new Map<string, GroupMember[]>();
  for (const member of members) {
    const list = byParent.get(member.parentKey) ?? [];
    list.push(member);
    byParent.set(member.parentKey, list);
  }

  for (const group of byParent.values()) {
    group.sort((a, b) => a.top - b.top);
    const countBoost = Math.min(0.18, Math.max(0, group.length - 1) * 0.025);
    const familyCounts = new Map<string, number>();
    for (const member of group) {
      familyCounts.set(member.sourceFamily, (familyCounts.get(member.sourceFamily) ?? 0) + 1);
    }

    const widths = group.map((x) => x.width).filter((x) => x > 0);
    const avgWidth = widths.length ? widths.reduce((a, b) => a + b, 0) / widths.length : 0;
    const centers = group.map((x) => x.centerX);
    const avgCenter = centers.length ? centers.reduce((a, b) => a + b, 0) / centers.length : 0;

    for (const member of group) {
      let boost = countBoost;
      if ((familyCounts.get(member.sourceFamily) ?? 0) >= 3) boost += 0.08;
      if (avgWidth > 0 && Math.abs(member.width - avgWidth) / avgWidth < 0.12) boost += 0.05;
      if (avgWidth > 0 && Math.abs(member.centerX - avgCenter) / avgWidth < 0.08) boost += 0.05;
      result.set(member.id, clamp01(member.baseScore + boost));
    }
  }
  return result;
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}
