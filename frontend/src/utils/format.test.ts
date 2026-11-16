import { describe, expect, it } from 'vitest'
import { formatMoney, formatNumber, formatPercent, formatPrice, formatQuantity, formatSigned, gainLossClass } from './format'

describe('format', () => {
  it('formats prices with 2 decimals, 4 below 1', () => {
    expect(formatPrice(1234.5)).toBe('1,234.50')
    expect(formatPrice(0.12345)).toBe('0.1235')
    expect(formatPrice(-3)).toBe('−3.00')
    expect(formatPrice(null)).toBe('—')
    expect(formatPrice(Number.NaN)).toBe('—')
  })

  it('formats signed amounts and percentages', () => {
    expect(formatSigned(12.3)).toBe('+12.30')
    expect(formatSigned(-12.3)).toBe('−12.30')
    expect(formatSigned(0)).toBe('0.00')
    expect(formatSigned(undefined)).toBe('—')
    expect(formatPercent(1.5)).toBe('+1.50%')
    expect(formatPercent(-0.256)).toBe('−0.26%')
    expect(formatPercent(null)).toBe('—')
  })

  it('formats money, numbers and quantities', () => {
    expect(formatMoney(1000000)).toBe('1,000,000.00')
    expect(formatNumber(-2.345)).toBe('−2.35')
    expect(formatQuantity(10)).toBe('10')
    expect(formatQuantity(0.12345678)).toBe('0.12345678')
  })

  it('colours gains green and losses red', () => {
    expect(gainLossClass(1)).toContain('emerald')
    expect(gainLossClass(-1)).toContain('red')
    expect(gainLossClass(0)).toBe('text-slate-700')
    expect(gainLossClass(null)).toBe('text-slate-700')
  })
})
