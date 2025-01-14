# Cargo Management App

## Overview

The **Cargo Management App** is a powerful tool designed to streamline logistics and transportation workflows. This app provides features for managing services, tracking orders, and optimizing transport modes across various operations.

## Features

- **Service Type Management**: Define and manage various service types.
- **Transport Modes**: Support for multiple transport modes like Road, Rail, and more.
- **Sales Order Types**: Differentiate between Domestic, Export, and Import orders.
- **Sequence Tracking**: Maintain the order of operations for services.

## Installation

### Prerequisites

- Frappe Framework installed
- A MariaDB database set up

### Steps to Install

1. Clone the repository into your apps directory:
   ```bash
   bench get-app cargo_management
   ```
2. Install the app on your site:
   ```bash
   bench --site [your-site-name] install-app cargo_management
   ```
3. Apply the setup SQL (optional for default configuration):
   ```sql
   INSERT INTO `tabService Type` (`name`, `name1`, `transport_mode`, `applicable`, `job_type`)
   VALUES
   ('82ghk3ttss', 'Shifting', '', 0, 'Road'),
   ('eo0ldr6jda', 'Gate Out', '', 0, 'Yard'),
   ('enrhva2nvi', 'Gate In', '', 0, 'Yard'),
   ('giml5efmsh', 'Long Haul', 'Road (Truck)', 0, 'Road'),
   ('b8mpmejmts', 'Empty Pickup', 'Rail (Train)', 0, 'Road'),
   ('vg2osur4ei', 'First Mile', 'Rail (Train)', 0, 'Road'),
   ('l6cdsvneqs', 'Cross Stuff', 'Road (Truck)', 0, 'Cross Stuff'),
   ('l645t4f4fm', 'Cross Stuff', 'Rail (Train)', 0, 'Cross Stuff'),
   ('l5if4pva8b', 'Empty Return', 'Road (Truck)', 0, 'Road'),
   ('l5dbk4s5u4', 'Empty Return', 'Rail (Train)', 0, 'Road'),
   ('oasikqkqg2', 'Short Haul', 'Road (Truck)', 0, 'Road'),
   ('oapcdu6gv3', 'Empty Pickup', 'Road (Truck)', 0, 'Road'),
   ('oalds7gjs7', 'Last Mile', 'Rail (Train)', 0, 'Road'),
   ('oagb0ddmuo', 'Middle Mile', 'Rail (Train)', 0, 'Rail');
   ```

## Usage

1. Access the app via the desk in your Frappe instance.
2. Navigate to the **Service Type** section to view and manage available services.
3. Use the **Transport Mode** and **Sales Order Type** to classify and filter operations.

## Development

### Setting Up a Development Environment

1. Clone the repository locally:
   ```bash
   git clone [repo-url]
   cd cargo_management
   ```
2. Set up the app in a local Frappe bench instance:
   ```bash
   bench start
   ```

### Contributing

We welcome contributions! Please submit a pull request with a detailed description of your changes.

## License

This project is licensed under the MIT License.

## Support

For support or inquiries, contact: [[osama.ahmed@deliverydevs.com](mailto\:osama.ahmed@deliverydevs.com)].



