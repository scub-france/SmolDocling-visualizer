@ui @regression
Feature: UI — Doc workspace: the document shows in the analysis viewer (#352)

  # /docs/:id used to show one page image at a time with its own ‹ › bar.
  # It now uses the Parse view's viewer, sized from GET /api/documents/:id/pages,
  # so it works before any analysis.

  Background:
    * url baseUrl

  Scenario: Multi-page document → viewer on page 1 → next page → page 2
    * def upload = call read('classpath:common/helpers/upload.feature') { file: 'medium.pdf' }
    * def docId = upload.docId

    # The page sizes come from the PDF itself, no analysis needed.
    Given url baseUrl
    And path '/api/documents', docId, 'pages'
    When method GET
    Then status 200
    And assert karate.sizeOf(response) > 1

    * driver uiBaseUrl + '/docs/' + docId
    * waitFor('[data-e2e=document-viewer] [data-e2e=preview-with-overlay]')
    * waitFor('[data-e2e=preview-page-1]')
    * waitUntil("document.querySelector('[data-e2e=page-input]').value === '1'")

    * click('[data-e2e=page-next]')
    * waitUntil("document.querySelector('[data-e2e=page-input]').value === '2'")

    * call read('classpath:common/helpers/cleanup-by-name.feature') { filename: 'medium.pdf' }
