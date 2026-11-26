extends Control

var taps := 0


func _on_tap_pressed() -> void:
	taps += 1
	$Count.text = "Taps: %d" % taps
