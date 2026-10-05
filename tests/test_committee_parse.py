

def test_cio_number_is_the_labelled_line_not_a_percent_quoted_in_the_reasoning():
    import committee
    raw = ("CIO_Decision: I sided with the Economist.\n"
           "Grounding_Summary: Driven by SPY's 12-month return of +33.5% and low uncertainty.\n"
           "SPY_Expected_Return_Percent: 5.0\nTLT_Expected_Return_Percent: 2.5\nCIO_Confidence: Medium\n")
    fields, problems = committee.parse_cio(raw)
    assert not problems and fields["spy_q"] == 5.0 and fields["tlt_q"] == 2.5
