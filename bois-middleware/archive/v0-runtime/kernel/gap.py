class GapDetector:

    def detect(self, bois_output):

        return len(bois_output.get("required_information", [])) > 0
