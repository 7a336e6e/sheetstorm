/** @jest-environment node */
// Example of a pure-logic test: the node environment is faster than jsdom and
// is enough for code that does not touch the DOM.
import { escapeHtml, sanitizeText, sanitizeUrl, stripHtml } from './sanitize'

describe('sanitize', () => {
  it('escapes every HTML-significant character', () => {
    expect(escapeHtml(`<a href="x" title='y'>&</a>`)).toBe(
      '&lt;a href=&quot;x&quot; title=&#x27;y&#x27;&gt;&amp;&lt;&#x2F;a&gt;'
    )
  })

  it('strips tags and trims plain-text fields', () => {
    expect(stripHtml('<b>bold</b> text')).toBe('bold text')
    expect(sanitizeText('  <script>x</script>title  ')).toBe('xtitle')
  })

  it.each([
    ['https://example.com/a?b=1', 'https://example.com/a?b=1'],
    ['  http://example.com  ', 'http://example.com'],
    ['javascript:alert(1)', ''],
    ['data:text/html,<b>x</b>', ''],
    ['not a url', ''],
    ['', ''],
  ])('sanitizeUrl(%p) -> %p', (input, expected) => {
    expect(sanitizeUrl(input)).toBe(expected)
  })
})
