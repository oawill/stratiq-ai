/** Configurable annual discount: annual price per month = monthly * (1 - discount). */
export const ANNUAL_DISCOUNT = 0.2;

export function annualMonthly(monthly: number, discount = ANNUAL_DISCOUNT): number {
  return Math.round(monthly * (1 - discount) * 100) / 100;
}
export function annualTotal(monthly: number, discount = ANNUAL_DISCOUNT): number {
  return Math.round(monthly * 12 * (1 - discount) * 100) / 100;
}
