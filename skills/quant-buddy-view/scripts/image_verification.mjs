export function staticImageProblems(html) {
  const text = String(html || '');
  const problems = [];
  if (/__QB_IMAGE_[A-Z0-9_]+__/.test(text)) problems.push('图片 marker 残留');
  if (/(?:<img\b[^>]*\bsrc\s*=\s*["']|url\(\s*["']?)http:\/\//i.test(text)) problems.push('图片 URL 禁止使用 http://');
  return problems;
}

export function imageElementProblems(images = []) {
  return images
    .filter(image => !/^data:image\//i.test(String(image.src || '')))
    .filter(image => image.complete !== true || Number(image.naturalWidth || 0) <= 0)
    .map(image => ({ src: String(image.src || ''), complete: !!image.complete, naturalWidth: Number(image.naturalWidth || 0) }));
}
