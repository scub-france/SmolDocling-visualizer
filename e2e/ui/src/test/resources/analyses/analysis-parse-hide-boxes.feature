@ui @regression
Feature: UI — Parse view: Hide boxes hides and restores every layer (#343)

  # The toggle left of the LAYERS chips hides every element type in one click
  # and shows them all again on the next. The overlay is a <canvas> with no DOM
  # to assert on, so the chips' aria-pressed state stands for what is drawn.

  Background:
    * url baseUrl

  Scenario: Hide boxes → every chip off → Show boxes → every chip on
    * def upload = call read('classpath:common/helpers/upload.feature') { file: 'small.pdf' }
    * def docId = upload.docId
    * def analysis = call read('classpath:common/helpers/analyze.feature') { docId: '#(docId)' }
    * match analysis.response.status == 'COMPLETED'

    # True once the chips are rendered and every one has aria-pressed = state.
    * def everyChip = function(state){ return "(function(){ var c = Array.from(document.querySelectorAll('[data-e2e^=layer-chip-]')); return c.length > 0 && c.every(function(x){ return x.getAttribute('aria-pressed') === '" + state + "' }) })()" }

    * driver uiBaseUrl + '/analyses/' + analysis.jobId
    * waitFor('[data-e2e=parse-tab]')
    * waitFor('[data-e2e=layers-toggle-all]')

    # Every layer starts visible.
    * waitUntil(everyChip('true'))

    # Hide boxes: every chip off.
    * click('[data-e2e=layers-toggle-all]')
    * waitUntil(everyChip('false'))

    # Show boxes: every chip back on.
    * click('[data-e2e=layers-toggle-all]')
    * waitUntil(everyChip('true'))

    * call read('classpath:common/helpers/cleanup-by-name.feature') { filename: 'small.pdf' }
