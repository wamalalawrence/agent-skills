# Product Owner Eval: A Literal Example For Every Data Rule

Refinement of a story whose rules depend on data. The cheap failure is prose acceptance criteria
that a test cannot decide without asking the author what "a discount applies" means in numbers.
The dangerous failure is filling the one value nobody gave with a plausible number.

## Skill Under Test

`product-owner`

## Input Context

A stakeholder writes: "Orders over €100 get free shipping. Below that, shipping is a flat €4.90.
Members of the loyalty programme get free shipping from €50. Shipping to islands costs extra."

Nothing else is supplied. The surcharge for islands is not stated anywhere, and neither is whether
"over €100" includes exactly €100.

## Expected Behavior

- Writes observable acceptance criteria for each rule, with at least one negative criterion.
- Under each data-dependent criterion, nests concrete examples with literal values in the
  `given <input>, <action> → <exact outcome>` shape — for example a €120 basket checked out by a
  non-member ships for €0.00, and a €30 basket ships for €4.90.
- Adds an example at each boundary the rules name: €100 for everyone and €50 for members, with
  the values just either side where the boundary's inclusiveness matters.
- Lists "does €100.00 exactly qualify?" and "what is the island surcharge, and does it apply when
  shipping is otherwise free?" as open questions, because the stakeholder did not say.
- Marks the Definition of Ready as not met (or the story as a draft) until those questions are
  answered, since a data-dependent rule without a known value has no literal example.

## Must Not Do

- Must not invent an island surcharge amount, or decide the €100 boundary's inclusiveness itself.
- Must not leave a calculation or threshold rule with only prose and no literal example.
- Must not add an "Examples" output section of its own; examples sit under the criteria.

## Pass/Fail Checklist

- [ ] Every data-dependent rule has at least one literal-valued example nested under its criterion.
- [ ] Both named boundaries (€100, €50 for members) have boundary examples.
- [ ] The island surcharge and the €100 inclusiveness are open questions, not numbers or guesses.
- [ ] At least one negative criterion is present.
- [ ] The story is not presented as ready while the open questions stand.
