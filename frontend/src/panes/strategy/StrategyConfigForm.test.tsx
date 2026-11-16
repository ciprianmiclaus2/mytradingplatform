import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it } from 'vitest'
import type { StrategyParameter } from '../../types/api'
import { initialFormValues, type FormValues } from './config'
import { StrategyConfigForm } from './StrategyConfigForm'

const parameters: StrategyParameter[] = [
  { name: 'window', type: 'integer', title: 'Window', description: 'Sessions used.', default: 20, minimum: 2, maximum: 500, choices: null },
  { name: 'threshold', type: 'number', title: 'Threshold', description: 'Signal level.', default: 1.5, minimum: 0, maximum: null, choices: null },
  { name: 'label', type: 'string', title: 'Label', description: 'Free text.', default: 'abc', minimum: null, maximum: null, choices: null },
  { name: 'mode', type: 'string', title: 'Mode', description: 'Pick one.', default: 'slow', minimum: null, maximum: null, choices: ['fast', 'slow'] },
  { name: 'enabled', type: 'boolean', title: 'Enabled', description: 'Turn on.', default: true, minimum: null, maximum: null, choices: null },
]

function Harness({ errors = {} }: { errors?: Record<string, string> }) {
  const [values, setValues] = useState<FormValues>(initialFormValues(parameters, {}))
  return (
    <>
      <StrategyConfigForm idPrefix="t" parameters={parameters} values={values} errors={errors} onChange={(n, v) => setValues((s) => ({ ...s, [n]: v }))} />
      <output data-testid="values">{JSON.stringify(values)}</output>
    </>
  )
}

describe('StrategyConfigForm', () => {
  it('generates an input for every parameter type with defaults, limits and descriptions', () => {
    render(<Harness />)
    const window = screen.getByLabelText(/Window/)
    expect(window).toHaveAttribute('type', 'number')
    expect(window).toHaveAttribute('step', '1')
    expect(window).toHaveAttribute('min', '2')
    expect(window).toHaveAttribute('max', '500')
    expect(window).toHaveValue(20)
    expect(screen.getByText('(2 – 500)')).toBeInTheDocument()

    const threshold = screen.getByLabelText(/Threshold/)
    expect(threshold).toHaveAttribute('step', 'any')
    expect(threshold).toHaveValue(1.5)
    expect(threshold).not.toHaveAttribute('max')
    expect(screen.getByText('(≥ 0)')).toBeInTheDocument()

    expect(screen.getByLabelText(/Label/)).toHaveValue('abc')
    expect(screen.getByLabelText(/Mode/).tagName).toBe('SELECT')
    expect(screen.getByLabelText(/Mode/)).toHaveValue('slow')
    expect(screen.getByLabelText('Enabled')).toBeChecked()

    expect(screen.getByText(/Sessions used\. Default: 20\./)).toBeInTheDocument()
    expect(window).toHaveAccessibleDescription(/Sessions used/)
  })

  it('reports edits for each type', async () => {
    render(<Harness />)
    await userEvent.clear(screen.getByLabelText(/Window/))
    await userEvent.type(screen.getByLabelText(/Window/), '30')
    await userEvent.selectOptions(screen.getByLabelText(/Mode/), 'fast')
    await userEvent.click(screen.getByLabelText('Enabled'))
    expect(JSON.parse(screen.getByTestId('values').textContent!)).toMatchObject({ window: '30', mode: 'fast', enabled: false })
  })

  it('shows field errors', () => {
    render(<Harness errors={{ window: 'Must be at least 2' }} />)
    expect(screen.getByText('Must be at least 2')).toBeInTheDocument()
    expect(screen.getByLabelText(/Window/)).toHaveAttribute('aria-invalid', 'true')
  })
})
