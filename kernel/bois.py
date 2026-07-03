class BOIS:

    def reason(self, sima_output, memory):

        uncertainty = sima_output["uncertainty"]

        required_information = []

        if uncertainty > 0.6:
            required_information.append("need_more_input")

        return {
            "hypotheses": [
                "H1_based_on_context",
                "H2_general_reasoning"
            ],
            "required_information": required_information,
            "plan": "minimal_test_first"
        }
