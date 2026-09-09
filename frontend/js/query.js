/**
 * Query Helper Module — SatQuery AI
 * Handles user input extraction from form fields
 */

const Query = {
  /**
   * Get current location search query from input field
   */
  currentLocationQuery() {
    const input = document.getElementById('location-input');
    if (!input) return '';
    return input.value?.trim() || '';
  },

  /**
   * Get current question from question input field
   */
  currentQuestion() {
    const input = document.getElementById('question-input');
    if (!input) return '';
    return input.value?.trim() || '';
  },

  /**
   * Set location query
   */
  setLocationQuery(value) {
    const input = document.getElementById('location-input');
    if (!input) return;
    input.value = value || '';
  },

  /**
   * Set question query
   */
  setQuestionQuery(value) {
    const input = document.getElementById('question-input');
    if (!input) return;
    input.value = value || '';
  },

  /**
   * Clear all queries
   */
  clearAll() {
    this.setLocationQuery('');
    this.setQuestionQuery('');
  }
};

// Export for global use
window.Query = Query;
