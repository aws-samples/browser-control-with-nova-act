from nova_act import NovaAct


def test_simple_action():
    """Simple test to check browser start and stop functionality."""
    # Initialize NovaAct client
    nova = NovaAct(starting_page="https://www.google.com")
    
    try:
        # Start the browser
        print("Starting browser...")
        nova.start()
        print("Browser started successfully!")
        
        # Perform one simple action
        print("Performing search action...")
        nova.act("search for python")
        print("Action completed!")
        
    except Exception as e:
        print(f"Error occurred: {e}")
        
    finally:
        # Stop the browser
        print("Stopping browser...")
        nova.stop()
        print("Browser stopped successfully!")


if __name__ == "__main__":
    test_simple_action()
