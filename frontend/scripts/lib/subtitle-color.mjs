// Read the same CSS as the preview instead of maintaining a second preset palette.
export async function captionAssColor(page) {
  const color = await page.locator(".caption").evaluate(element => getComputedStyle(element).color);
  const channels = /^rgb\(\s*(\d+),\s*(\d+),\s*(\d+)\s*\)$/.exec(color)?.slice(1).map(Number);
  if (!channels || channels.some(channel => channel > 255)) {
    throw new Error(`Unsupported subtitle color: ${color}`);
  }
  // ASS uses alpha + blue + green + red; these template colors are opaque.
  return "&H00" + channels.reverse().map(channel => channel.toString(16).padStart(2, "0")).join("").toUpperCase();
}
