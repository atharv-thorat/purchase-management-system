// Exact decimal arithmetic for form PREVIEWS and pre-filled defaults only — the server's figures
// are always the authority and replace these on save. Floats are avoided because a pre-filled
// invoice total that disagrees with the server's rounding by a paisa would cause a false
// MISMATCH (2.5 × 10.01 = 25.025: float rounding gives 25.02, the server's half-up gives 25.03).

const PATTERN = /^\d+(\.\d+)?$/;

/** "2.5" at 3 places → 2500n. Null for anything that isn't a plain non-negative decimal. */
function toScaled(value: string, places: number): bigint | null {
  const text = value.trim();
  if (!PATTERN.test(text)) return null;
  const [whole, fraction = ""] = text.split(".");
  if (fraction.length > places) return null;
  return BigInt(whole + fraction.padEnd(places, "0"));
}

function fromScaled(value: bigint, places: number): string {
  const negative = value < 0n;
  const digits = (negative ? -value : value).toString().padStart(places + 1, "0");
  const text = places ? `${digits.slice(0, -places)}.${digits.slice(-places)}` : digits;
  return negative ? `-${text}` : text;
}

/** qty × price rounded half up to the paisa — the same rule as the server's line_amount (D-53). */
export function lineAmount(qty: string, price: string): string | null {
  const q = toScaled(qty, 3); // thousandths
  const p = toScaled(price, 2); // paise
  if (q === null || p === null) return null;
  return fromScaled((q * p + 500n) / 1000n, 2);
}

export function sumMoney(values: (string | null)[]): string {
  return fromScaled(values.reduce<bigint>((sum, v) => sum + (v ? toScaled(v, 2) ?? 0n : 0n), 0n), 2);
}

/** a − b for quantities (3 places); null if either isn't a number. */
export function subtractQty(a: string, b: string): string | null {
  const x = toScaled(a || "0", 3);
  const y = toScaled(b || "0", 3);
  return x === null || y === null ? null : fromScaled(x - y, 3);
}

export function isPositive(value: string): boolean {
  const scaled = toScaled(value, 3);
  return scaled !== null && scaled > 0n;
}
