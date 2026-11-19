/** Base64 of bytes, or a string taken to be base64 already. No Buffer: browsers. */
export function base64(value: Uint8Array | string): string {
  if (typeof value === 'string') return value;
  let binary = '';
  for (let i = 0; i < value.length; i += 0x8000) {
    binary += String.fromCharCode(...value.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

/** A path segment from a caller's value. An id with a `/` in it must not
 *  reach a different route. */
export function seg(value: string): string {
  return encodeURIComponent(value);
}
