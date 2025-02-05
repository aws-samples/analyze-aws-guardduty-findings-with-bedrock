import json
import boto3
import os
import logging
from botocore.exceptions import ClientError

# Set up logging details
logger = logging.getLogger()
logger.setLevel(logging.INFO)

bedrock = boto3.client('bedrock-runtime')
ses = boto3.client('ses')
SENDER_EMAIL = os.environ['SENDER_EMAIL']
RECEIVER_EMAIL = os.environ['RECEIVER_EMAIL']

def get_severity_info(severity):
    """
    Get severity level and color based on severity value
    """
    try:
        if severity is None:
            return {'level': 'Unknown', 'color': '#808080'}
            
        severity_value = float(severity)
        severity_mapping = {
            8.0: {'level': 'High', 'color': '#DC0000'},
            5.0: {'level': 'Medium', 'color': '#FF832B'},
            2.0: {'level': 'Low', 'color': '#F1C21B'}
        }
        
        return next(
            (info for threshold, info in severity_mapping.items() 
             if severity_value >= threshold),
            {'level': 'Low', 'color': '#F1C21B'}
        )
    except (ValueError, TypeError):
        return {'level': 'Unknown', 'color': '#808080'}

def handler(event, context):
    print(event)
    logger.info(f"Received event: {json.dumps(event)}")

    for record in event['Records']:
        # Parse the SQS message body which contains the GuardDuty finding
        message = json.loads(record['body'])
        detail = message.get('detail', {})
        logger.info(f"Processing finding detail: {json.dumps(detail)}")
        
        # Extract fields from the correct location in the event structure
        account_id = detail.get('accountId', 'Unknown Account')
        finding_id = detail.get('id', 'Unknown Finding ID')
        region = detail.get('region', 'Unknown Region')
        severity = detail.get('severity')
        finding_type = detail.get('type', 'Unknown Type')
        title = detail.get('title', 'Unknown Title')
        description = detail.get('description', 'Unknown Description')
        print(description)
        # Extract resource details
        resource = detail.get('resource', {})
        resource_type = resource.get('resourceType', 'Unknown Resource Type')
        
        # Extract instance details
        instance_details = resource.get('instanceDetails', {})
        instance_id = instance_details.get('instanceId', 'N/A')
        instance_type = instance_details.get('instanceType', 'N/A')
        
        # Extract network details
        service_details = detail.get('service', {})
        action_details = service_details.get('action', {})
        network_details = action_details.get('networkConnectionAction', {})
        connection_direction = network_details.get('connectionDirection', 'N/A')
        remote_ip = network_details.get('remoteIpDetails', {}).get('ipAddressV4', 'N/A')
        remote_port = network_details.get('remotePortDetails', {}).get('port', 'N/A')
        protocol = network_details.get('protocol', 'N/A')
        
        # Extract time details
        event_first_seen = service_details.get('eventFirstSeen', 'N/A')
        event_last_seen = service_details.get('eventLastSeen', 'N/A')
        
        prompt = f"""Human: Analyze the following GuardDuty finding and provide a detailed response:

Finding Details:
- Type: {finding_type}
- Title: {title}
- Description: {description}
- Severity: {severity}
- Resource Type: {resource_type}
- Instance ID: {instance_id}
- Instance Type: {instance_type}
- Connection Direction: {connection_direction}
- Remote IP: {remote_ip}
- Remote Port: {remote_port}
- Protocol: {protocol}
- First Seen: {event_first_seen}
- Last Seen: {event_last_seen}

Please provide:
1. A concise overview of the finding
2. Assessment of potential security impact
3. Specific recommended actions for remediation
4. Additional security best practices to prevent similar incidents

Full finding details:
{json.dumps(detail, indent=2)}"""
        
        try:
            logger.info("Invoking Bedrock with Claude 3.5 Sonnet model")
            response = bedrock.invoke_model(
                modelId='anthropic.claude-3-sonnet-20240229-v1:0',
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 1000,
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "temperature": 0.1,
                    "top_p": 1,
                    "top_k": 250
                })
            )
            
            summary = json.loads(response['body'].read())['content'][0]['text']
            logger.info(f"Generated summary: {summary}")
            
            severity_info = get_severity_info(severity)
            
            html_body = f"""
            <html>
              <head>
                <style>
                  body {{
                    font-family: 'Segoe UI', Arial, sans-serif;
                    line-height: 1.6;
                    color: #2d2d2d;
                    max-width: 800px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f8f9fa;
                  }}
                  .container {{
                    background-color: #ffffff;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                    overflow: hidden;
                  }}
                  .header {{
                    background-color: {severity_info['color']};
                    color: white;
                    padding: 25px;
                    text-align: center;
                    border-bottom: 3px solid rgba(0, 0, 0, 0.1);
                  }}
                  .header h2 {{
                    margin: 0;
                    font-size: 24px;
                    text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);
                  }}
                  .content {{
                    padding: 20px;
                  }}
                  .finding-details {{
                    background-color: #f8f9fa;
                    padding: 20px;
                    border-radius: 6px;
                    margin-bottom: 20px;
                    border: 1px solid #e9ecef;
                  }}
                  .severity-badge {{
                    background-color: {severity_info['color']};
                    color: white;
                    padding: 6px 12px;
                    border-radius: 20px;
                    display: inline-block;
                    font-weight: bold;
                    text-transform: uppercase;
                    font-size: 0.85em;
                    letter-spacing: 0.5px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                  }}
                  .section {{
                    background-color: white;
                    padding: 20px;
                    margin-bottom: 20px;
                    border-radius: 6px;
                    border: 1px solid #e9ecef;
                  }}
                  .section h3 {{
                    color: #2d2d2d;
                    margin-top: 0;
                    border-bottom: 2px solid {severity_info['color']};
                    padding-bottom: 8px;
                    display: inline-block;
                  }}
                  .resource-details {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                    gap: 15px;
                    margin-top: 15px;
                  }}
                  .detail-item {{
                    background-color: #f8f9fa;
                    padding: 12px;
                    border-radius: 4px;
                    border-left: 3px solid {severity_info['color']};
                  }}
                  .footer {{
                    text-align: center;
                    padding: 20px;
                    background-color: #f8f9fa;
                    border-top: 1px solid #e9ecef;
                    color: #6c757d;
                    font-size: 0.9em;
                  }}
                  .ai-generated {{
                    margin-top: 15px;
                    padding: 15px;
                    background-color: #e8f4f8;
                    border-radius: 6px;
                    text-align: center;
                    color: #456;
                    font-style: italic;
                  }}
                  .timestamp {{
                    color: #6c757d;
                    font-size: 0.9em;
                    margin-top: 5px;
                  }}
                </style>
              </head>
              <body>
                <div class="container">
                  <div class="header">
                    <h2>⚠️ GuardDuty Finding Alert</h2>
                  </div>
                  
                  <div class="content">
                    <div class="finding-details">
                      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <strong>AWS Account: {account_id}</strong>
                        <span class="severity-badge">{severity_info['level']} ({severity})</span>
                      </div>
                      <div class="resource-details">
                        <div class="detail-item">
                          <strong>Finding ID:</strong><br>{finding_id}
                        </div>
                        <div class="detail-item">
                          <strong>Region:</strong><br>{region}
                        </div>
                        <div class="detail-item">
                          <strong>Resource Type:</strong><br>{resource_type}
                        </div>
                      </div>
                    </div>

                    <div class="section">
                      <h3>Finding Details</h3>
                      <p><strong>Title:</strong> {title}</p>
                      <p><strong>Description:</strong> {description}</p>
                    </div>

                    <div class="section">
                      <h3>Resource Information</h3>
                      <div class="resource-details">
                        <div class="detail-item">
                          <strong>Instance ID:</strong><br>{instance_id}
                        </div>
                        <div class="detail-item">
                          <strong>Instance Type:</strong><br>{instance_type}
                        </div>
                      </div>
                    </div>

                    <div class="section">
                      <h3>Network Details</h3>
                      <div class="resource-details">
                        <div class="detail-item">
                          <strong>Connection Direction:</strong><br>{connection_direction}
                        </div>
                        <div class="detail-item">
                          <strong>Remote IP:</strong><br>{remote_ip}
                        </div>
                        <div class="detail-item">
                          <strong>Remote Port:</strong><br>{remote_port}
                        </div>
                        <div class="detail-item">
                          <strong>Protocol:</strong><br>{protocol}
                        </div>
                      </div>
                    </div>

                    <div class="section">
                      <h3>AI Analysis of GuardDuty finding</h3><br>
                      {summary.replace('\n', '<br>')}
                    </div>

                    <div class="timestamp">
                      <strong>First Seen:</strong> {event_first_seen}<br>
                      <strong>Last Seen:</strong> {event_last_seen}
                    </div>

                    <div class="ai-generated">
                      <strong>Note:</strong> This analysis was generated using Amazon Bedrock Generative AI service
                    </div>
                  </div>

                  <div class="footer">
                    <p>For detailed information, please visit the AWS GuardDuty console.</p>
                    <p>This is an automated security notification. Please do not reply to this email.</p>
                  </div>
                </div>
              </body>
            </html>
            """
            
            text_body = f"""
            GuardDuty Finding Summary and Recommendations

            Account ID: {account_id}
            Finding ID: {finding_id}
            Region: {region}
            Type: {finding_type}
            Severity: {severity_info['level']} ({severity})
            
            Instance Details:
            Instance ID: {instance_id}
            Instance Type: {instance_type}

            Network Details:
            Connection Direction: {connection_direction}
            Remote IP: {remote_ip}
            Remote Port: {remote_port}
            Protocol: {protocol}

            Finding Details:
            Title: {title}
            Description: {description}

            Time Details:
            First Seen: {event_first_seen}
            Last Seen: {event_last_seen}

            AI Analysis and Recommendations:
            {summary}

            Note: This analysis was generated using Amazon Bedrock Generative AI service.

            For more details, please check the AWS GuardDuty console.

            This is an automated security notification. Please do not reply to this email.
            """
            
            logger.info("Sending summary via SES")
            ses.send_email(
                Source=SENDER_EMAIL,
                Destination={
                    'ToAddresses': [RECEIVER_EMAIL]
                },
                Message={
                    'Subject': {
                        'Data': f'GuardDuty Alert: {severity_info["level"]} Severity Finding in Account {account_id}'
                    },
                    'Body': {
                        'Text': {
                            'Data': text_body
                        },
                        'Html': {
                            'Data': html_body
                        }
                    }
                }
            )
            logger.info("Summary sent successfully")

        except ClientError as e:
            logger.error(f"Error processing GuardDuty finding: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON: {e}")
        except KeyError as e:
            logger.error(f"Key error in response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")

    logger.info("Finished processing all records")
    return {
        'statusCode': 200,
        'body': json.dumps('Processing completed successfully')
    }
