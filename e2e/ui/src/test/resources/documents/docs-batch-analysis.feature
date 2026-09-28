@ui @regression
Feature: UI — Docs library: analyse several documents at once (#354)

  # Select documents in /docs and click Analyze: one analysis starts per
  # document, and the Analysis library opens and refreshes their statuses
  # until they end, without a reload.

  Background:
    * url baseUrl

  Scenario: Select two documents → Analyze → both analyses complete in the library
    * def small = call read('classpath:common/helpers/upload.feature') { file: 'small.pdf' }
    * def medium = call read('classpath:common/helpers/upload.feature') { file: 'medium.pdf' }

    # The selection is the UI action under test, so it goes through the page.
    * driver uiBaseUrl + '/docs'
    * waitFor('[data-e2e=docs-table]')
    * click("[data-doc-id='" + small.docId + "'] [data-e2e=doc-select]")
    * click("[data-doc-id='" + medium.docId + "'] [data-e2e=doc-select]")
    * waitFor('[data-e2e=docs-bulk-bar]')
    * click('[data-e2e=docs-analyze-selected]')

    # A first analysis can take minutes while the models load: longer budget.
    * waitForUrl('/analyses')
    * retry(300, 1000).waitFor("[data-document-id='" + small.docId + "'] [data-e2e=analysis-status][data-status=COMPLETED]")
    * retry(300, 1000).waitFor("[data-document-id='" + medium.docId + "'] [data-e2e=analysis-status][data-status=COMPLETED]")

    * call read('classpath:common/helpers/cleanup-by-name.feature') { filename: 'small.pdf' }
    * call read('classpath:common/helpers/cleanup-by-name.feature') { filename: 'medium.pdf' }
