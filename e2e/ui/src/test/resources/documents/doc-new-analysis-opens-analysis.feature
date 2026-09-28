@ui @regression
Feature: UI — Doc workspace: New analysis opens the analysis once it completes (#342)

  # Launching an analysis from /docs/:id used to leave the user on the
  # document once it finished. The workspace now opens the new analysis on
  # its Parse view, and Back returns to the document.

  Background:
    * url baseUrl

  Scenario: New analysis → lands on the analysis → Back returns to the document
    * def upload = call read('classpath:common/helpers/upload.feature') { file: 'small.pdf' }
    * def docId = upload.docId

    # The launch is the UI action under test, so it goes through the page.
    * driver uiBaseUrl + '/docs/' + docId
    * waitFor('[data-e2e=workspace-new-analysis]')
    * click('[data-e2e=workspace-new-analysis]')

    # The Parse view only exists on /analyses/:id. A first analysis can take
    # minutes while the models load, so this wait gets a longer budget.
    * retry(300, 1000).waitFor('[data-e2e=parse-tab]')
    * waitForUrl('/analyses/')

    # router.push, not replace: Back returns to the document workspace.
    * back()
    * waitForUrl('/docs/' + docId)
    * waitFor('[data-e2e=document-viewer]')

    * call read('classpath:common/helpers/cleanup-by-name.feature') { filename: 'small.pdf' }
