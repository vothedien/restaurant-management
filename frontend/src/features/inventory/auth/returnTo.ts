function unsafeCharacters(value: string) {
  return value.includes('\\') || Array.from(value).some(character => character.charCodeAt(0) < 32 || character.charCodeAt(0) === 127);
}
export function inventoryReturnTo(value: string | null | undefined) {
  if (!value || !value.startsWith('/') || value.startsWith('//') || unsafeCharacters(value)) return '/inventory';
  try {
    const url = new URL(value, 'https://inventory.invalid');
    if (url.origin !== 'https://inventory.invalid' || /%(?:2f|5c|25)/i.test(url.pathname)) return '/inventory';
    const pathname = decodeURIComponent(url.pathname);
    if (unsafeCharacters(pathname)) return '/inventory';
    if ((pathname !== '/inventory' && !pathname.startsWith('/inventory/')) || pathname === '/inventory/login' || pathname.startsWith('/inventory/login/')) return '/inventory';
    return url.pathname + url.search + url.hash;
  } catch { return '/inventory'; }
}
