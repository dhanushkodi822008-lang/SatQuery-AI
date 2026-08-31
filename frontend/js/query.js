/** Query helpers */
function currentLocationQuery() {
  return (document.getElementById('location-input')?.value || '').trim();
}
function currentQuestion() {
  return (document.getElementById('question-input')?.value || '').trim();
}
window.Query = { currentLocationQuery, currentQuestion };
