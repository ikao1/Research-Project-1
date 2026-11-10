// automask_vision: Apple Vision segmentation for the Look Decomposer auto mask.
//
// usage: automask_vision <subject|people> <input image> <output.png>
//
// subject  foreground subject(s) (VNGenerateForegroundInstanceMaskRequest, macOS 14+)
// people   person segmentation (VNGeneratePersonSegmentationRequest, accurate)
//
// Writes an 8-bit grayscale PNG the size of the input: white = selected.
// Built by: python3 -m look_decomposer.automask --build

import Foundation
import Vision
import CoreImage
import ImageIO
import UniformTypeIdentifiers

func fail(_ message: String, _ code: Int32) -> Never {
    FileHandle.standardError.write((message + "\n").data(using: .utf8)!)
    exit(code)
}

let args = CommandLine.arguments
guard args.count == 4 else {
    fail("usage: automask_vision <subject|people> <input> <output.png>", 2)
}
let mode = args[1]
let inputPath = args[2]
let outputPath = args[3]

guard let source = CGImageSourceCreateWithURL(URL(fileURLWithPath: inputPath) as CFURL, nil),
      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
    fail("cannot read \(inputPath)", 1)
}

let handler = VNImageRequestHandler(cgImage: image, options: [:])
var maskImage: CIImage

do {
    if mode == "subject" {
        let request = VNGenerateForegroundInstanceMaskRequest()
        try handler.perform([request])
        guard let observation = request.results?.first else {
            fail("no subject found", 3)
        }
        let buffer = try observation.generateScaledMaskForImage(
            forInstances: observation.allInstances, from: handler)
        maskImage = CIImage(cvPixelBuffer: buffer)
    } else if mode == "people" {
        let request = VNGeneratePersonSegmentationRequest()
        request.qualityLevel = .accurate
        request.outputPixelFormat = kCVPixelFormatType_OneComponent8
        try handler.perform([request])
        guard let observation = request.results?.first as? VNPixelBufferObservation else {
            fail("no person found", 3)
        }
        maskImage = CIImage(cvPixelBuffer: observation.pixelBuffer)
    } else {
        fail("unknown mode \(mode); use subject or people", 2)
    }
} catch {
    fail("Vision failed: \(error)", 4)
}

// Match the mask to the input image size.
let width = CGFloat(image.width)
let height = CGFloat(image.height)
let scaled = maskImage.transformed(by: CGAffineTransform(
    scaleX: width / maskImage.extent.width,
    y: height / maskImage.extent.height))

let context = CIContext()
let rect = CGRect(x: 0, y: 0, width: width, height: height)
guard let output = context.createCGImage(scaled, from: rect, format: CIFormat.L8,
                                         colorSpace: CGColorSpaceCreateDeviceGray()) else {
    fail("could not render the mask", 5)
}
guard let destination = CGImageDestinationCreateWithURL(
        URL(fileURLWithPath: outputPath) as CFURL, UTType.png.identifier as CFString, 1, nil) else {
    fail("cannot write \(outputPath)", 5)
}
CGImageDestinationAddImage(destination, output, nil)
guard CGImageDestinationFinalize(destination) else {
    fail("cannot write \(outputPath)", 5)
}
print("ok \(Int(width))x\(Int(height))")
