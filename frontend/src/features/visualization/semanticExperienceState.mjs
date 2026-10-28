/** Display only the newest private card per target that has no valid adoption. */
export function pendingExperienceDrafts(drafts, adoptions = {}) {
  const seen = new Set();
  return drafts.filter(draft => {
    const kind = draft.target_kind || 'object';
    const key = `${kind}:${draft.target_id}`;
    if (draft.confirmed || seen.has(key) || (kind === 'correction' && adoptions[draft.target_id]?.length)) return false;
    seen.add(key);
    return true;
  });
}
