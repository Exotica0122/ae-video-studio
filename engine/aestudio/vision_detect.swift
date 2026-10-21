// Faces, people and text in each image, as JSON boxes normalised to 0–1 with a top-left origin.
import Foundation
import Vision

func box(_ r: CGRect) -> [Double] {
    [Double(r.minX), Double(1 - r.maxY), Double(r.width), Double(r.height)]
}

var results: [[String: Any]] = []
for path in CommandLine.arguments.dropFirst() {
    let faces = VNDetectFaceRectanglesRequest()
    let humans = VNDetectHumanRectanglesRequest()
    humans.upperBodyOnly = false
    let text = VNRecognizeTextRequest()
    text.recognitionLevel = .accurate
    text.usesLanguageCorrection = false
    let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:])
    do {
        try handler.perform([faces, humans, text])
        results.append([
            "path": path,
            "faces": (faces.results ?? []).map { box($0.boundingBox) },
            "humans": (humans.results ?? []).map { box($0.boundingBox) },
            "text": (text.results ?? []).map {
                ["box": box($0.boundingBox), "string": $0.topCandidates(1).first?.string ?? ""] as [String: Any]
            },
        ])
    } catch {
        results.append(["path": path, "error": "\(error)"])
    }
}
let data = try! JSONSerialization.data(withJSONObject: results)
print(String(data: data, encoding: .utf8)!)
