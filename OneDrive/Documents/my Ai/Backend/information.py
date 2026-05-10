import cv2
import mediapipe as mp
import sys

# Initialize the camera
cap = cv2.VideoCapture(0)

# Check if camera opened successfully
if not cap.isOpened():
    print("Error: Could not open camera. Please check if camera is connected and not being used by another application.")
    sys.exit(1)

# Initialize MediaPipe Hands
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(static_image_mode=False, max_num_hands=2, min_detection_confidence=0.5)
mp_drawing = mp.solutions.drawing_utils

try:
    while True:
        # Capture frame-by-frame
        ret, frame = cap.read()
        if not ret:
            print("Failed to grab frame")
            break

        # Convert the frame to RGB
        image_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # Process the frame with MediaPipe Hands
        results = hands.process(image_rgb)

        # Draw the hand landmarks and connections
        if results.multi_hand_landmarks:
            for hand_landmarks in results.multi_hand_landmarks:
                mp_drawing.draw_landmarks(
                    frame, hand_landmarks, mp_hands.HAND_CONNECTIONS,
                    mp_drawing.DrawingSpec(color=(0, 255, 0), thickness=2, circle_radius=2),
                    mp_drawing.DrawingSpec(color=(0, 0, 255), thickness=2))

                # Get the position of the thumb tip (landmark 4)
                thumb_tip = hand_landmarks.landmark[4]
                h, w, c = frame.shape
                thumb_x, thumb_y = int(thumb_tip.x * w), int(thumb_tip.y * h)

                # Display real-time information on the thumb tip
                cv2.putText(frame, "Real-Time Info", (thumb_x + 10, thumb_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 0), 2)

        # Display the resulting frame
        cv2.imshow('Hand Detection and Real-Time Info', frame)

        # Break the loop if 'q' is pressed
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

except KeyboardInterrupt:
    print("\nProgram interrupted by user")
except Exception as e:
    print(f"An error occurred: {e}")
finally:
    # Release the camera and close all OpenCV windows
    if cap.isOpened():
        cap.release()
    cv2.destroyAllWindows()
    hands.close()
    print("Camera released and windows closed")