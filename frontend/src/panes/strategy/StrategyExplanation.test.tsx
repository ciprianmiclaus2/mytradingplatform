import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { StrategyExplanation } from './StrategyExplanation'

describe('StrategyExplanation', () => {
  it('renders paragraphs, headings and bullet lists', () => {
    const text = 'First paragraph\ncontinues here.\n\n## Signals\n\n- BUY when low.\n- SELL when high.\n\nClosing note.'
    const { container } = render(<StrategyExplanation text={text} />)
    expect(screen.getByRole('heading', { name: 'Signals' })).toBeInTheDocument()
    expect(screen.getAllByRole('listitem').map((li) => li.textContent)).toEqual(['BUY when low.', 'SELL when high.'])
    expect(container.querySelectorAll('p')[0]).toHaveTextContent('First paragraph continues here.')
    expect(screen.getByText('Closing note.')).toBeInTheDocument()
  })

  it('never renders HTML from the text', () => {
    const { container } = render(<StrategyExplanation text={'<img src=x onerror=alert(1)> <b>bold</b>'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(container).toHaveTextContent('<img src=x onerror=alert(1)> <b>bold</b>')
  })

  it('handles an empty explanation', () => {
    render(<StrategyExplanation text="  " />)
    expect(screen.getByText(/No explanation is available/)).toBeInTheDocument()
  })
})
