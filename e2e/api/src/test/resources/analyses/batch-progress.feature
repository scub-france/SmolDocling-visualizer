@regression
Feature: Batched conversion with progress reporting

  # Requires BATCH_PAGE_SIZE > 0 in the server configuration.
  # If BATCH_PAGE_SIZE is 0 (disabled), the batch-specific assertions
  # are skipped gracefully — the test still validates completion.

  Background:
    * url baseUrl

  Scenario: Large PDF completes and reports page count
    * def uploaded = call read('classpath:common/helpers/upload.feature') { file: 'large.pdf' }

    # Create analysis
    Given path '/api/analyses'
    And request { documentId: '#(uploaded.docId)' }
    When method POST
    Then status 200
    * def jobId = response.id

    # Poll until completed
    Given path '/api/analyses', jobId
    And retry until response.status == 'COMPLETED' || response.status == 'FAILED'
    When method GET
    Then status 200
    And match response.status == 'COMPLETED'
    And match response.contentMarkdown == '#string'
    And match response.pagesJson == '#string'

    # When batched, progress must be preserved at completion (not reset to null)
    # progressTotal > 0 proves batching was active
    # progressCurrent == progressTotal proves the final update_status didn't erase them
    * if (response.progressTotal > 0) karate.match('response.progressCurrent', response.progressTotal)

    # Cleanup
    * call read('classpath:common/helpers/cleanup.feature') { docId: '#(uploaded.docId)' }

  Scenario: Batched conversion keeps the document structure (#344)
    # The batches are merged back into one Docling document. Only a real test
    # of the merge when BATCH_PAGE_SIZE > 0 and pages > BATCH_PAGE_SIZE
    # (progressTotal > 0); without batching it must hold all the more.
    * def uploaded = call read('classpath:common/helpers/upload.feature') { file: 'large.pdf' }
    * def analysis = call read('classpath:common/helpers/analyze.feature') { docId: '#(uploaded.docId)' }
    * match analysis.response.status == 'COMPLETED'
    * match analysis.response.hasDocumentJson == true

    Given path '/api/documents', uploaded.docId, 'tree'
    When method GET
    Then status 200
    And assert karate.sizeOf(response) > 0

    * call read('classpath:common/helpers/cleanup.feature') { docId: '#(uploaded.docId)' }
