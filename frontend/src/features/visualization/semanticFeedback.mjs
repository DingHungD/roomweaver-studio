/** Submit only changed answers when no particular Q button supplied an ID. */
export function changedQuestionIds(answers,marks,savedAnswers,savedMarks){
 const ids=new Set([...Object.keys(answers),...Object.keys(marks)]);
 return [...ids].filter(id=>(answers[id]||'').trim()||(marks[id]||[]).length).filter(id=>
  (answers[id]||'')!==(savedAnswers[id]||'')||JSON.stringify(marks[id]||[])!==JSON.stringify(savedMarks[id]||[]));
}
